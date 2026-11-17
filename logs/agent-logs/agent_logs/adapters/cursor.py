"""Cursor (IDE and CLI ``cursor-agent``): agent transcripts plus metadata stores.

Spec: skills/plugins/ai-tools-knowledge/skills/cursor-logs/{SKILL.md,format.md}

- Root: ``AGENT_LOGS_CURSOR_DIR`` > ``CURSOR_CONFIG_DIR`` > ``~/.cursor``.
- A (source of truth, IDE and CLI): ``projects/<enc-cwd>/agent-transcripts/<sid>/<sid>.jsonl``;
  subagents ``<sid>/subagents/<id>.jsonl`` become sessions with ``source="subagent"`` and
  ``parent_id=<sid>``. Records have no timestamps/model/usage/tool results: event time is
  the ``<timestamp>`` tag of the last user line (minute precision).
- B (CLI): ``chats/<md5(cwd)>/<chatId>/meta.json`` (+ ``store.db`` table ``meta`` for
  ``name`` / ``lastUsedModel`` / ``createdAt``; chats with only ``store.db`` get their cwd by
  matching the ``md5(cwd)`` group dir). Only used to fill cwd/title/model/times; message blobs,
  ``prompt_history.json`` and ``*EncryptionKey`` are never read out.
- C (IDE): ``<appdata>/Cursor/User/globalStorage/state.vscdb``. Only ``composerHeaders``
  (one bounded SELECT of narrow columns) and ``cursorDiskKV`` primary-key lookups of
  ``composerData:<id>`` for the model name. Bubble bodies and ``ItemTable`` are not read.
- A session id found in B is ``source="cli"``, in C ``source="ide"``, else ``"transcript"``.
- Project is the cwd from B/C; the lossy ``<enc-cwd>`` dir name is only used to map to a
  cwd already known from B/C (case-insensitive). Tokens/cost are not available (``None``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_logs.adapters.base import Adapter
from agent_logs.model import Event, Filters, Session, SourceInfo
from agent_logs.paths import appdata, home, list_dir, mtime, normalize_path
from agent_logs.readers import dumps_compact, iter_jsonl, open_sqlite, read_json, text_of
from agent_logs.timeutil import parse_cursor_ts, parse_ts

_TS_TAG = re.compile(r"<timestamp>(.*?)</timestamp>", re.S)
_QUERY_TAG = re.compile(r"<user_query>\s*(.*?)\s*(?:</user_query>|$)", re.S)
_TITLE_MAX = 80


@dataclass
class _Meta:
    """Supplementary metadata for one session id from B or C."""

    source: str
    cwd: str | None = None
    title: str | None = None
    model: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    path: str | None = None


def enc_cwd(cwd: str) -> str:
    """Cursor's (lossy) ``projects/<enc-cwd>`` name for a cwd, lower-cased for matching."""
    return re.sub(r"[^A-Za-z0-9]+", "-", cwd).strip("-").lower()


class CursorAdapter(Adapter):
    name = "cursor"
    env_var = "AGENT_LOGS_CURSOR_DIR"

    def __init__(self) -> None:
        super().__init__()
        self._cli: dict[str, _Meta] | None = None
        self._ide: dict[str, _Meta] | None = None

    def root(self) -> Path:
        env = os.environ.get(self.env_var)
        if env:
            return Path(env)
        if os.environ.get("CURSOR_CONFIG_DIR") and not os.environ.get("AGENT_LOGS_HOME"):
            return Path(os.environ["CURSOR_CONFIG_DIR"])
        return home() / ".cursor"

    def ide_db(self) -> Path:
        return appdata() / "Cursor" / "User" / "globalStorage" / "state.vscdb"

    # ------------------------------------------------------------ discovery

    def _transcripts(self) -> Iterator[tuple[Path, Path, str | None]]:
        """``(jsonl, project dir, parent id or None)`` for main and subagent transcripts."""
        for proj in list_dir(self.root() / "projects"):
            tdir = proj / "agent-transcripts"
            if not proj.is_dir() or not tdir.is_dir():
                continue
            for sdir in list_dir(tdir):
                if not sdir.is_dir():
                    continue
                main = sdir / f"{sdir.name}.jsonl"
                if main.is_file() and main in list_dir(sdir):
                    yield main, proj, None
                for sub in list_dir(sdir / "subagents"):
                    if sub.is_file() and sub.suffix == ".jsonl":
                        yield sub, proj, sdir.name

    def _chat_dirs(self) -> Iterator[Path]:
        for group in list_dir(self.root() / "chats"):
            if group.is_dir():
                for chat in list_dir(group):
                    if chat.is_dir():
                        yield chat

    def detect(self) -> list[SourceInfo]:
        root = self.root()
        files = [f for f, _p, _parent in self._transcripts()]
        last = max((m for m in (mtime(f) for f in files) if m), default=None)
        out = [
            SourceInfo(
                self.name,
                "transcript",
                str(root / "projects"),
                (root / "projects").is_dir(),
                len(files),
                last,
                note=f"agent-transcripts (main + subagents); root via {self.env_var} / "
                "CURSOR_CONFIG_DIR / ~/.cursor",
            )
        ]
        chats = list(self._chat_dirs())
        last_c = max((m for m in (mtime(c / "meta.json") for c in chats) if m), default=None)
        out.append(
            SourceInfo(
                self.name,
                "cli",
                str(root / "chats"),
                (root / "chats").is_dir(),
                len(chats),
                last_c,
                note="CLI chats; metadata only (cwd/title/model/times)",
            )
        )
        db = self.ide_db()
        count = None
        if db.is_file():
            count = len(self._ide_meta())
        out.append(
            SourceInfo(
                self.name,
                "ide",
                str(db),
                db.is_file(),
                count,
                mtime(db),
                note="IDE composerHeaders; metadata only, bubble bodies not read",
            )
        )
        return out

    # ------------------------------------------------------------ metadata (B / C)

    def _cli_meta(self) -> dict[str, _Meta]:
        if self._cli is not None:
            return self._cli
        out: dict[str, _Meta] = {}
        groups: dict[str, str] = {}
        for chat in self._chat_dirs():
            meta_path = chat / "meta.json"
            meta = read_json(meta_path) if meta_path.is_file() else None
            store = chat / "store.db"
            has_store = store.is_file() and store in list_dir(chat)
            if not isinstance(meta, dict):
                if not has_store:
                    continue
                meta = {}  # some chats have only store.db: cwd resolved via md5 below
            m = _Meta(
                source="cli",
                cwd=_str(meta.get("cwd")),
                title=_str(meta.get("title")),
                started_at=parse_ts(meta.get("createdAtMs")),
                ended_at=parse_ts(meta.get("updatedAtMs")),
                path=str(meta_path if meta else store),
            )
            if has_store:
                try:
                    sm = self._store_meta(store)
                except (sqlite3.Error, OSError, ValueError) as exc:
                    self.warn(f"{store}: {type(exc).__name__}: {exc}")
                    sm = {}
                m.model = _str(sm.get("lastUsedModel"))
                m.title = m.title or _str(sm.get("name"))
                m.started_at = m.started_at or parse_ts(sm.get("createdAt"))
            out[chat.name] = m
            groups[chat.name] = chat.parent.name
        # chat group dir = md5(cwd): recover cwd for chats without meta.json
        by_md5 = {
            hashlib.md5(m.cwd.encode("utf-8")).hexdigest(): m.cwd for m in out.values() if m.cwd
        }
        for cid, m in out.items():
            if m.cwd is None:
                m.cwd = by_md5.get(groups[cid])
        self._cli = out
        return out

    @staticmethod
    def _store_meta(store: Path) -> dict[str, Any]:
        """Only ``name``, ``lastUsedModel`` and ``createdAt`` from the hex-JSON ``meta`` row (no keys)."""
        with open_sqlite(store) as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = '0'").fetchone()
        if row is None or row[0] is None:
            return {}
        raw = row[0]
        if isinstance(raw, bytes):
            raw = raw.decode("ascii", errors="replace")
        data = json.loads(bytes.fromhex(str(raw)).decode("utf-8", errors="replace"))
        if not isinstance(data, dict):
            return {}
        return {k: data.get(k) for k in ("name", "lastUsedModel", "createdAt")}

    def _ide_meta(self) -> dict[str, _Meta]:
        if self._ide is not None:
            return self._ide
        out: dict[str, _Meta] = {}
        db = self.ide_db()
        if db.is_file():
            try:
                out = self._read_ide(db)
            except (sqlite3.Error, OSError) as exc:
                self.warn(f"{db}: {type(exc).__name__}: {exc}")
        self._ide = out
        return out

    def _read_ide(self, db: Path) -> dict[str, _Meta]:
        out: dict[str, _Meta] = {}
        ws_root = db.parent.parent / "workspaceStorage"
        ws_cache: dict[str, str | None] = {}
        with open_sqlite(db) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ('composerHeaders', 'cursorDiskKV')"
                )
            }
            if "composerHeaders" in tables:
                rows = conn.execute(
                    "SELECT composerId, workspaceId, createdAt, lastUpdatedAt, "
                    "json_extract(value, '$.name'), "
                    "json_extract(value, '$.workspaceIdentifier.uri.fsPath') "
                    "FROM composerHeaders WHERE json_valid(value) OR value IS NULL"
                )
            elif "cursorDiskKV" in tables:
                # older layout: composerData:* rows (indexed key range, narrow columns)
                rows = conn.execute(
                    "SELECT substr(key, 14), json_extract(value, '$.workspaceIdentifier.id'), "
                    "json_extract(value, '$.createdAt'), json_extract(value, '$.lastUpdatedAt'), "
                    "json_extract(value, '$.name'), "
                    "json_extract(value, '$.workspaceIdentifier.uri.fsPath') "
                    "FROM cursorDiskKV WHERE key >= 'composerData:' AND key < 'composerData;' "
                    "AND json_valid(value)"
                )
            else:
                return out
            for cid, wsid, created, updated, title, fs_path in rows:
                if not cid:
                    continue
                cwd = _str(fs_path)
                if cwd is None and wsid:
                    if wsid not in ws_cache:
                        ws_cache[wsid] = self._workspace_folder(ws_root, str(wsid))
                    cwd = ws_cache[wsid]
                out[str(cid)] = _Meta(
                    source="ide",
                    cwd=cwd,
                    title=_str(title),
                    started_at=parse_ts(created),
                    ended_at=parse_ts(updated),
                    path=str(db),
                )
        return out

    def _ide_models(self, ids: list[str]) -> dict[str, str]:
        """``composerData:<id>`` primary-key lookups for ``modelConfig.modelName``."""
        db = self.ide_db()
        if not ids or not db.is_file():
            return {}
        out: dict[str, str] = {}
        try:
            with open_sqlite(db) as conn:
                if "cursorDiskKV" not in {
                    r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }:
                    return out
                for i in range(0, len(ids), 500):
                    chunk = [f"composerData:{x}" for x in ids[i : i + 500]]
                    marks = ",".join("?" * len(chunk))
                    for key, model in conn.execute(
                        "SELECT key, CASE WHEN json_valid(value) THEN "
                        "json_extract(value, '$.modelConfig.modelName') END "
                        f"FROM cursorDiskKV WHERE key IN ({marks})",
                        chunk,
                    ):
                        if _str(model):
                            out[key[len("composerData:") :]] = model
        except (sqlite3.Error, OSError) as exc:
            self.warn(f"{db}: model lookup failed ({type(exc).__name__}: {exc})")
        return out

    @staticmethod
    def _workspace_folder(ws_root: Path, wsid: str) -> str | None:
        data = read_json(ws_root / wsid / "workspace.json")
        if not isinstance(data, dict):
            return None
        uri = data.get("folder") or data.get("workspace")
        return normalize_path(uri) if isinstance(uri, str) else None

    # ------------------------------------------------------------ sessions

    def iter_sessions(self, filters: Filters) -> Iterator[Session]:
        items = []
        for f, proj, parent in self._transcripts():
            if filters.since:
                m = mtime(f)
                if m and m < filters.since:
                    continue
            items.append((f, proj, parent))
        if not items:
            return
        cli, ide = self._cli_meta(), self._ide_meta()
        ide_ids = [f.stem for f, _p, _parent in items if f.stem in ide and f.stem not in cli]
        models = self._ide_models(ide_ids)
        by_enc: dict[str, str] = {}
        for m in list(ide.values()) + list(cli.values()):
            if m.cwd:
                by_enc.setdefault(enc_cwd(m.cwd), m.cwd)
        for f, proj, parent in items:
            sid = f.stem
            meta = cli.get(sid) or ide.get(sid)
            s = Session(id=sid, tool=self.name, parent_id=parent, path=str(f), ref=f)
            if parent:
                s.source = "subagent"
            else:
                s.source = meta.source if meta else "transcript"
            if meta:
                s.cwd, s.title = meta.cwd, meta.title
                s.started_at, s.ended_at = meta.started_at, meta.ended_at
                s.model = meta.model or models.get(sid)
            if s.cwd is None:
                s.cwd = by_enc.get(proj.name.lower())
            s = self._summarize(f, s)
            if s:
                yield s

    def _summarize(self, path: Path, s: Session) -> Session | None:
        msgs = calls = 0
        first_ts = last_ts = None
        first_query = None
        try:
            for ev in self._walk(path, s.id):
                if ev.ts:
                    first_ts = ev.ts if first_ts is None or ev.ts < first_ts else first_ts
                    last_ts = ev.ts if last_ts is None or ev.ts > last_ts else last_ts
                if ev.kind == "message" and ev.role in ("user", "assistant"):
                    msgs += 1
                    if ev.role == "user" and first_query is None and ev.text:
                        first_query = _query_text(ev.text)
                elif ev.kind == "tool_call":
                    calls += 1
        except OSError as exc:
            self.warn(f"{path}: {exc}")
            return None
        s.started_at = s.started_at or first_ts
        s.ended_at = s.ended_at or last_ts or mtime(path)
        if s.started_at and s.ended_at and s.ended_at < s.started_at:
            s.ended_at = s.started_at
        if not s.title and first_query:
            line = first_query.strip().splitlines()[0] if first_query.strip() else ""
            s.title = line[:_TITLE_MAX] or None
        s.project = normalize_path(s.cwd)
        s.message_count, s.tool_call_count = msgs, calls
        return s

    # ------------------------------------------------------------ events

    def iter_events(self, session: Session) -> Iterator[Event]:
        path = session.ref if isinstance(session.ref, Path) else Path(session.path or "")
        yield from self._walk(path, session.id)

    def _walk(self, path: Path, sid: str) -> Iterator[Event]:
        ts: datetime | None = None
        for rec in iter_jsonl(path):
            base: dict[str, Any] = dict(session_id=sid, tool=self.name, raw=rec)
            if rec.get("type") == "turn_ended":
                status = _str(rec.get("status"))
                err = _str(rec.get("error"))
                text = f"{status}: {err}" if status and err else (status or err)
                yield Event(ts=ts, role="system", kind="turn_end", text=text, **base)
                continue
            role = rec.get("role")
            msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            content = msg.get("content")
            if role not in ("user", "assistant") or content is None:
                yield Event(ts=ts, role=None, kind="raw", text=None, **base)
                continue
            blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
            if role == "user":
                for b in blocks:
                    if isinstance(b, dict) and b.get("type") == "text":
                        t = _tag_ts(b.get("text"))
                        if t:
                            ts = t
                            break
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    yield Event(
                        ts=ts, role=role, kind="message", text=text_of(b.get("text")), **base
                    )
                elif bt == "tool_use":
                    inp = b.get("input")
                    yield Event(
                        ts=ts,
                        role="assistant",
                        kind="tool_call",
                        tool_name=_str(b.get("name")),
                        call_id=_str(b.get("id")),
                        text=dumps_compact(inp) if inp is not None else None,
                        **base,
                    )
                elif bt in ("thinking", "reasoning"):
                    yield Event(
                        ts=ts,
                        role=role,
                        kind="reasoning",
                        text=text_of(b.get("thinking") or b.get("text")),
                        **base,
                    )
                else:
                    yield Event(ts=ts, role=role, kind="raw", text=None, **base)


def _tag_ts(text: Any) -> datetime | None:
    if not isinstance(text, str):
        return None
    m = _TS_TAG.search(text)
    if not m:
        return None
    return parse_cursor_ts(m.group(1)) or parse_ts(m.group(1))


def _query_text(text: str) -> str:
    m = _QUERY_TAG.search(text)
    if m:
        return m.group(1)
    return _TS_TAG.sub("", text)


def _str(v: Any) -> str | None:
    return v if isinstance(v, str) and v.strip() else None
