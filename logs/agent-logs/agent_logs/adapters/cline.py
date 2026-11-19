"""Cline (VS Code extension / Cline CLI): two storage systems, both read.

Spec: skills/plugins/ai-tools-knowledge/skills/cline-logs/SKILL.md

- Data root: ``AGENT_LOGS_CLINE_DIR`` > ``CLINE_DATA_DIR`` (ignored when ``AGENT_LOGS_HOME``
  is set) > ``~/.cline/data``.
- A. SDK sessions (CLI and newer extension): ``<data>/sessions/<sid>/<sid>.json`` (meta) +
  ``<sid>.messages.json`` (conversation). The JSON files are canonical; the index
  ``<data>/db/sessions.db`` only adds parent/subagent links and rows whose directory is
  gone. ``Session.source`` is the recorded ``source`` (cli / vscode / ...), default ``sdk``.
  Extra ``*.messages.json`` in a session dir become ``source="subagent"`` sessions.
- B. Legacy task format: ``<editor>/User/globalStorage/saoudrizwan.claude-dev/`` under
  ``appdata()`` (``state/taskHistory.json`` + ``tasks/<id>/``) -> ``source="vscode-legacy"``
  (``cursor-legacy`` etc. for forks), and ``<data>/tasks/`` (old CLI / JetBrains) ->
  ``source="cli-legacy"``. Events come from ``ui_messages.json`` (``partial`` entries are
  skipped); ``api_conversation_history.json`` is not read.
- De-duplication: a legacy task whose id is an SDK session id, or is referenced by an SDK
  session's ``metadata.legacyTask`` / ``migratedFromLegacyTask``, is skipped (A wins).
- Tokens/cost: A counts ``metrics`` once per assistant message id; the session total is
  the larger of ``metadata.usage`` and that sum (``metadata.usage`` was observed to cover
  only the last run of a resumed session). B puts each ``api_req_started`` /
  ``deleted_api_reqs`` on a ``usage`` event; the session total prefers ``taskHistory``.
- Never opened: ``<data>/secrets.json``, ``<data>/settings/`` (providers.json),
  ``globalState.json``; the data root is never scanned as a whole.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agent_logs.adapters.base import Adapter
from agent_logs.model import Event, Filters, Session, SourceInfo
from agent_logs.paths import appdata, home, is_link_like, list_dir, mtime, normalize_path
from agent_logs.readers import dumps_compact, open_sqlite, read_json, table_names, text_of
from agent_logs.timeutil import parse_ts

_EXT_ID = "saoudrizwan.claude-dev"
# editor folder under appdata() -> legacy source name
_EDITORS = {
    "Code": "vscode-legacy",
    "Code - Insiders": "vscode-insiders-legacy",
    "VSCodium": "vscodium-legacy",
    "Cursor": "cursor-legacy",
    "Windsurf": "windsurf-legacy",
}
_SECRET_NAMES = {"secrets.json", "providers.json", "globalState.json"}
_TITLE_LEN = 80
_TOK_KEYS = ("tokens_in", "tokens_out", "tokens_cache_read", "tokens_cache_write")


class ClineAdapter(Adapter):
    name = "cline"
    env_var = "AGENT_LOGS_CLINE_DIR"

    def root(self) -> Path:
        env = os.environ.get(self.env_var)
        if env:
            return Path(env)
        if os.environ.get("CLINE_DATA_DIR") and not os.environ.get("AGENT_LOGS_HOME"):
            return Path(os.environ["CLINE_DATA_DIR"])
        return home() / ".cline" / "data"

    def _legacy_roots(self) -> list[tuple[str, Path, Path]]:
        """``(source, tasks_dir, taskHistory.json)`` for every legacy location."""
        out = []
        for editor, source in _EDITORS.items():
            base = appdata() / editor / "User" / "globalStorage" / _EXT_ID
            out.append((source, base / "tasks", base / "state" / "taskHistory.json"))
        tasks = self.root() / "tasks"
        out.append(("cli-legacy", tasks, tasks / "taskHistory.json"))
        return out

    # ------------------------------------------------------------ discovery

    def _sdk_dirs(self) -> list[Path]:
        return [p for p in list_dir(self.root() / "sessions") if p.is_dir()]

    def _task_dirs(self, tasks: Path) -> list[Path]:
        return [p for p in list_dir(tasks) if p.is_dir()]

    def detect(self) -> list[SourceInfo]:
        root = self.root()
        dirs = self._sdk_dirs()
        last = max((m for m in (mtime(d) for d in dirs) if m), default=None)
        out = [
            SourceInfo(
                self.name,
                "sdk",
                str(root / "sessions"),
                (root / "sessions").is_dir(),
                len(dirs),
                last,
                note=f"root via {self.env_var} / CLINE_DATA_DIR / ~/.cline/data",
            )
        ]
        db = root / "db" / "sessions.db"
        rows = None
        if db.is_file():
            rows = len(self._db_rows(db))
        out.append(
            SourceInfo(
                self.name,
                "sdk-index",
                str(db),
                db.is_file(),
                rows,
                mtime(db),
                note="index only; JSON is canonical",
            )
        )
        for source, tasks, _hist in self._legacy_roots():
            if source != "vscode-legacy" and not tasks.is_dir():
                continue  # only list the default editor when absent
            tdirs = self._task_dirs(tasks)
            last = max((m for m in (mtime(d) for d in tdirs) if m), default=None)
            out.append(SourceInfo(self.name, source, str(tasks), tasks.is_dir(), len(tdirs), last))
        return out

    def _db_rows(self, db: Path) -> dict[str, dict[str, Any]]:
        try:
            with open_sqlite(db, mode="ro") as conn:
                if "sessions" not in table_names(conn):
                    return {}
                cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
                want = [
                    c
                    for c in (
                        "session_id",
                        "source",
                        "started_at",
                        "ended_at",
                        "model",
                        "cwd",
                        "workspace_root",
                        "prompt",
                        "metadata_json",
                        "messages_path",
                        "parent_session_id",
                        "is_subagent",
                        "updated_at",
                    )
                    if c in cols
                ]
                if "session_id" not in want:
                    return {}
                rows = conn.execute(f"SELECT {', '.join(want)} FROM sessions").fetchall()
                return {r["session_id"]: dict(r) for r in rows if r["session_id"]}
        except Exception as exc:  # noqa: BLE001 - sqlite / copy errors
            self.warn(f"{db}: {exc}")
            return {}

    # ------------------------------------------------------------ sessions

    def iter_sessions(self, filters: Filters) -> Iterator[Session]:
        root = self.root()
        db = root / "db" / "sessions.db"
        rows = self._db_rows(db) if db.is_file() else {}
        seen: set[str] = set()
        legacy_refs: set[str] = set()

        for d in self._sdk_dirs():
            sid = d.name
            seen.add(sid)
            meta_path = d / f"{sid}.json"
            msgs_path = d / f"{sid}.messages.json"
            meta = read_json(meta_path) if meta_path.is_file() else None
            if not isinstance(meta, dict):
                meta = None
            md = meta.get("metadata") if meta and isinstance(meta.get("metadata"), dict) else {}
            legacy_refs |= _legacy_ids(md)
            if filters.since:
                m = mtime(msgs_path) or mtime(meta_path)
                if m and m < filters.since:
                    continue
            if meta is None and not msgs_path.is_file():
                self.warn(f"{d}: no readable session json")
                continue
            s = self._sdk_session(sid, meta, rows.get(sid), meta_path, msgs_path)
            if s:
                yield s
            for extra in list_dir(d):
                n = extra.name
                if n.endswith(".messages.json") and n != msgs_path.name and extra.is_file():
                    sub = self._sdk_session(
                        n[: -len(".messages.json")],
                        None,
                        None,
                        extra,
                        extra,
                        parent=sid,
                        source="subagent",
                    )
                    if sub:
                        yield sub

        # index rows whose directory is gone
        for sid, row in rows.items():
            if sid in seen:
                continue
            seen.add(sid)
            md = _loads(row.get("metadata_json"))
            legacy_refs |= _legacy_ids(md if isinstance(md, dict) else {})
            mp = Path(row["messages_path"]) if row.get("messages_path") else None
            if mp is not None and (not mp.is_file() or is_link_like(mp)):
                mp = None
            s = self._sdk_session(sid, None, row, None, mp)
            if s:
                yield s

        for source, tasks, hist_path in self._legacy_roots():
            if not tasks.is_dir() and not hist_path.is_file():
                continue
            hist = read_json(hist_path) if hist_path.is_file() else None
            by_id = {}
            for h in hist if isinstance(hist, list) else []:
                if isinstance(h, dict) and h.get("id") is not None:
                    by_id[str(h["id"])] = h
            for td in self._task_dirs(tasks):
                tid = td.name
                if tid in seen or tid in legacy_refs:
                    continue
                seen.add(tid)
                ui = td / "ui_messages.json"
                if filters.since:
                    m = mtime(ui) or mtime(td)
                    if m and m < filters.since:
                        continue
                s = self._legacy_session(tid, source, td, by_id.get(tid))
                if s:
                    yield s

    def _sdk_session(
        self,
        sid: str,
        meta: dict | None,
        row: dict | None,
        meta_path: Path | None,
        msgs_path: Path | None,
        *,
        parent: str | None = None,
        source: str | None = None,
    ) -> Session | None:
        row = row or {}
        meta = meta or {}
        md = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else None
        if md is None:
            md = _loads(row.get("metadata_json"))
            md = md if isinstance(md, dict) else {}

        def pick(key: str) -> Any:
            v = meta.get(key)
            return v if v not in (None, "") else row.get(key)

        s = Session(id=sid, tool=self.name)
        s.source = source or pick("source") or "sdk"
        if s.source == "subagent" or row.get("is_subagent") in (1, True, "1"):
            s.source = "subagent"
        s.parent_id = parent or row.get("parent_session_id") or None
        s.cwd = pick("cwd")
        s.project = normalize_path(pick("workspace_root") or s.cwd)
        s.started_at = parse_ts(pick("started_at"))
        s.ended_at = parse_ts(pick("ended_at"))
        s.model = pick("model")
        title = md.get("title") or pick("prompt")
        s.title = _title(title)
        s.path = str(msgs_path or meta_path or "")
        s.ref = ("sdk", msgs_path)

        # walk messages for counts, per-message tokens, time range
        msgs = calls = 0
        sums: dict[str, Any] = dict.fromkeys((*_TOK_KEYS, "cost"))
        if msgs_path is not None and msgs_path.is_file():
            data = self._load(msgs_path)
            if data is None:
                return s if meta else None
            for ev in self._sdk_events(data, sid):
                if ev.kind == "message" and ev.role in ("user", "assistant"):
                    msgs += 1
                elif ev.kind == "tool_call":
                    calls += 1
                if ev.model and not s.model:
                    s.model = ev.model
                for k in sums:
                    v = getattr(ev, k)
                    if v is not None:
                        sums[k] = (sums[k] or 0) + v
                if ev.ts:
                    if s.started_at is None or ev.ts < s.started_at:
                        s.started_at = ev.ts
                    if s.ended_at is None or ev.ts > s.ended_at:
                        s.ended_at = ev.ts
            s.message_count, s.tool_call_count = msgs, calls

        usage = md.get("usage") if isinstance(md.get("usage"), dict) else None
        recorded: dict[str, Any] = {}
        if usage:
            recorded = {
                "tokens_in": _uncached(usage.get("inputTokens"), usage.get("cacheReadTokens")),
                "tokens_out": _int(usage.get("outputTokens")),
                "tokens_cache_read": _int(usage.get("cacheReadTokens")),
                "tokens_cache_write": _int(usage.get("cacheWriteTokens")),
                "cost": _float(usage.get("totalCost")),
            }
            if recorded["cost"] is None:
                recorded["cost"] = _float(md.get("totalCost"))
        chosen = sums
        if recorded and _volume(recorded) >= _volume(sums):
            chosen = recorded
        for k, v in chosen.items():
            setattr(s, k, v)
        if s.cost is None and parent is None:
            s.cost = _float(md.get("totalCost"))
        return s

    def _legacy_session(self, tid: str, source: str, td: Path, h: dict | None) -> Session | None:
        h = h or {}
        s = Session(id=tid, tool=self.name, source=source)
        ui_path = td / "ui_messages.json"
        s.path = str(ui_path)
        s.ref = ("legacy", ui_path, td)
        s.cwd = h.get("cwdOnTaskInitialization")
        s.project = normalize_path(s.cwd)
        s.model = h.get("modelId")
        s.title = _title(h.get("task"))
        if not s.model:
            tm = (
                self._load(td / "task_metadata.json")
                if (td / "task_metadata.json").is_file()
                else None
            )
            usage = tm.get("model_usage") if isinstance(tm, dict) else None
            if isinstance(usage, list) and usage and isinstance(usage[-1], dict):
                s.model = usage[-1].get("model_id")

        msgs = calls = 0
        sums: dict[str, Any] = dict.fromkeys((*_TOK_KEYS, "cost"))
        if ui_path.is_file():
            ui = self._load(ui_path)
            if ui is None and not h:
                return None
            for ev in self._legacy_events(ui if isinstance(ui, list) else [], tid):
                if ev.kind == "message" and ev.role in ("user", "assistant"):
                    msgs += 1
                    if s.title is None and ev.role == "user":
                        s.title = _title(ev.text)
                elif ev.kind == "tool_call":
                    calls += 1
                for k in sums:
                    v = getattr(ev, k)
                    if v is not None:
                        sums[k] = (sums[k] or 0) + v
                if ev.ts:
                    if s.started_at is None or ev.ts < s.started_at:
                        s.started_at = ev.ts
                    if s.ended_at is None or ev.ts > s.ended_at:
                        s.ended_at = ev.ts
            s.message_count, s.tool_call_count = msgs, calls
        elif not h:
            return None
        if s.started_at is None:
            s.started_at = parse_ts(h.get("ts")) or parse_ts(tid)

        recorded = {
            "tokens_in": _int(h.get("tokensIn")),
            "tokens_out": _int(h.get("tokensOut")),
            "tokens_cache_read": _int(h.get("cacheReads")),
            "tokens_cache_write": _int(h.get("cacheWrites")),
            "cost": _float(h.get("totalCost")),
        }
        chosen = recorded if any(v is not None for v in recorded.values()) else sums
        for k, v in chosen.items():
            setattr(s, k, v)
        return s

    def _load(self, path: Path) -> Any:
        """read_json with one retry (files are rewritten whole while a task runs)."""
        if path.name in _SECRET_NAMES or is_link_like(path):
            return None
        data = read_json(path)
        if data is None:
            data = read_json(path)
        if data is None:
            self.warn(f"{path}: unreadable JSON")
        return data

    # ------------------------------------------------------------ events

    def iter_events(self, session: Session) -> Iterator[Event]:
        ref = session.ref
        if not isinstance(ref, tuple):
            return
        if ref[0] == "sdk":
            path = ref[1]
            if path is None or not Path(path).is_file():
                return
            data = self._load(Path(path))
            if data is not None:
                yield from self._sdk_events(data, session.id)
        elif ref[0] == "legacy":
            path = ref[1]
            if not Path(path).is_file():
                return
            data = self._load(Path(path))
            if isinstance(data, list):
                yield from self._legacy_events(data, session.id)

    def _sdk_events(self, data: Any, sid: str) -> Iterator[Event]:
        messages = data.get("messages") if isinstance(data, dict) else data
        if not isinstance(messages, list):
            return
        tool_names: dict[str, str] = {}
        counted: set[str] = set()
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            ts = parse_ts(msg.get("ts"))
            content = msg.get("content")
            blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
            base = dict(session_id=sid, tool=self.name, ts=ts, raw=msg)
            if role == "assistant":
                mi = msg.get("modelInfo") if isinstance(msg.get("modelInfo"), dict) else {}
                model = mi.get("id")
                events: list[Event] = []
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    eb = dict(role="assistant", model=model, **base)
                    if bt == "text":
                        if b.get("text"):
                            events.append(Event(kind="message", text=text_of(b.get("text")), **eb))
                    elif bt in ("thinking", "redacted_thinking"):
                        events.append(
                            Event(kind="reasoning", text=text_of(b.get("thinking")), **eb)
                        )
                    elif bt == "tool_use":
                        if b.get("id") and b.get("name"):
                            tool_names[b["id"]] = b["name"]
                        events.append(
                            Event(
                                kind="tool_call",
                                tool_name=b.get("name"),
                                call_id=b.get("id"),
                                text=dumps_compact(b.get("input"))
                                if b.get("input") is not None
                                else None,
                                **eb,
                            )
                        )
                    else:
                        events.append(Event(kind="raw", **eb))
                metrics = msg.get("metrics") if isinstance(msg.get("metrics"), dict) else None
                mid = str(msg.get("id") or f"#{i}")
                if metrics and mid not in counted:
                    counted.add(mid)
                    if not events:
                        events.append(Event(kind="usage", role="assistant", model=model, **base))
                    e = events[0]
                    e.tokens_in = _uncached(
                        metrics.get("inputTokens"), metrics.get("cacheReadTokens")
                    )
                    e.tokens_out = _int(metrics.get("outputTokens"))
                    e.tokens_cache_read = _int(metrics.get("cacheReadTokens"))
                    e.tokens_cache_write = _int(metrics.get("cacheWriteTokens"))
                    e.cost = _float(metrics.get("cost"))
                yield from events
            elif role == "user":
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt == "text":
                        if b.get("text"):
                            yield Event(
                                role="user", kind="message", text=text_of(b.get("text")), **base
                            )
                    elif bt == "tool_result":
                        cid = b.get("tool_use_id")
                        yield Event(
                            role="tool",
                            kind="tool_result",
                            call_id=cid,
                            tool_name=b.get("name") or tool_names.get(cid),
                            text=text_of(b.get("content")),
                            **base,
                        )
                    else:
                        yield Event(role="user", kind="raw", **base)
            elif role == "system":
                yield Event(role="system", kind="system", text=text_of(content), **base)
            else:
                yield Event(kind="raw", **base)

    def _legacy_events(self, ui: list, sid: str) -> Iterator[Event]:
        for rec in ui:
            if not isinstance(rec, dict) or rec.get("partial"):
                continue
            ts = parse_ts(rec.get("ts"))
            mi = rec.get("modelInfo") if isinstance(rec.get("modelInfo"), dict) else {}
            model = mi.get("modelId")
            base = dict(session_id=sid, tool=self.name, ts=ts, raw=rec)
            text = rec.get("text")
            if rec.get("type") == "say":
                kind = rec.get("say")
                if kind in ("task", "user_feedback"):
                    yield Event(role="user", kind="message", text=text, **base)
                elif kind in ("text", "completion_result"):
                    if text:
                        yield Event(
                            role="assistant", kind="message", text=text, model=model, **base
                        )
                elif kind == "reasoning":
                    yield Event(role="assistant", kind="reasoning", text=text, model=model, **base)
                elif kind == "tool":
                    yield Event(
                        role="assistant",
                        kind="tool_call",
                        tool_name=_tool_of(text),
                        text=text,
                        model=model,
                        **base,
                    )
                elif kind == "command":
                    yield Event(
                        role="assistant",
                        kind="tool_call",
                        tool_name="execute_command",
                        text=text,
                        model=model,
                        **base,
                    )
                elif kind in ("use_mcp_server", "mcp_server_request_started"):
                    yield Event(
                        role="assistant",
                        kind="tool_call",
                        tool_name="use_mcp_server",
                        text=text,
                        model=model,
                        **base,
                    )
                elif kind == "command_output":
                    yield Event(
                        role="tool",
                        kind="tool_result",
                        tool_name="execute_command",
                        text=text,
                        **base,
                    )
                elif kind == "mcp_server_response":
                    yield Event(
                        role="tool",
                        kind="tool_result",
                        tool_name="use_mcp_server",
                        text=text,
                        **base,
                    )
                elif kind in ("api_req_started", "deleted_api_reqs"):
                    info = _loads(text)
                    info = info if isinstance(info, dict) else {}
                    yield Event(
                        role=None,
                        kind="usage",
                        text=kind,
                        model=model,
                        tokens_in=_int(info.get("tokensIn")),
                        tokens_out=_int(info.get("tokensOut")),
                        tokens_cache_read=_int(info.get("cacheReads")),
                        tokens_cache_write=_int(info.get("cacheWrites")),
                        cost=_float(info.get("cost")),
                        **base,
                    )
                else:
                    yield Event(role="system", kind="system", text=text or kind, **base)
            elif rec.get("type") == "ask":
                kind = rec.get("ask")
                if kind in ("followup", "completion_result", "plan_mode_respond"):
                    if text:
                        yield Event(
                            role="assistant", kind="message", text=text, model=model, **base
                        )
                    else:
                        yield Event(role="system", kind="system", text=kind, **base)
                elif kind == "tool":
                    yield Event(
                        role="assistant",
                        kind="tool_call",
                        tool_name=_tool_of(text),
                        text=text,
                        model=model,
                        **base,
                    )
                elif kind == "command":
                    yield Event(
                        role="assistant",
                        kind="tool_call",
                        tool_name="execute_command",
                        text=text,
                        model=model,
                        **base,
                    )
                elif kind == "use_mcp_server":
                    yield Event(
                        role="assistant",
                        kind="tool_call",
                        tool_name="use_mcp_server",
                        text=text,
                        model=model,
                        **base,
                    )
                else:
                    yield Event(role="system", kind="system", text=text or kind, **base)
            else:
                yield Event(kind="raw", **base)


# ------------------------------------------------------------ helpers


def _legacy_ids(md: dict) -> set[str]:
    out: set[str] = set()
    for key in ("legacyTask", "migratedFromLegacyTask", "legacyTaskId"):
        v = md.get(key)
        if isinstance(v, dict):
            v = v.get("id") or v.get("taskId")
        if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v):
            out.add(str(v))
    return out


def _tool_of(text: Any) -> str | None:
    info = _loads(text)
    return info.get("tool") if isinstance(info, dict) else None


def _loads(text: Any) -> Any:
    if not isinstance(text, str) or not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _title(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    line = value.strip().splitlines()[0].strip() if value.strip() else ""
    if not line:
        return None
    return line if len(line) <= _TITLE_LEN else line[: _TITLE_LEN - 1] + "…"


def _volume(d: dict[str, Any]) -> int:
    return sum(d.get(k) or 0 for k in ("tokens_in", "tokens_out"))


def _int(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _uncached(total, cache_read) -> int | None:
    """SDK ``inputTokens`` includes ``cacheReadTokens`` (observed in real data); the
    normalized ``tokens_in`` excludes cache reads like the other adapters."""
    t, c = _int(total), _int(cache_read)
    if t is not None and c is not None and t >= c:
        return t - c
    return t


def _float(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
