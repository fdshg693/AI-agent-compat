"""Google Antigravity (IDE / CLI ``agy``): ``~/.gemini/{antigravity,antigravity-cli,antigravity-ide}``.

Spec: skills/plugins/ai-tools-knowledge/skills/antigravity-logs/SKILL.md (+ format.md)

- Base: ``AGENT_LOGS_ANTIGRAVITY_DIR`` > ``~/.gemini``; the three roots below it are all
  scanned and conversations are de-duplicated by id. ``Session.source`` is the root name.
- Per conversation, 3-level fallback:
  1. body from ``brain/<id>/.system_generated/logs/transcript_full.jsonl``
     (else the truncated ``transcript.jsonl``);
  2. no transcript: metadata only from ``conversation_summaries.db`` (no events);
  3. ``conversations/<id>.db`` (protobuf) is not decoded in v1; only counted in ``detect()``.
- De-dup: the copy with a transcript wins (newest transcript mtime), else the summary row
  with the newest ``last_modified_time``. Title / workspace fall back to any root's summary.
  Title: user rename in ``annotations/<id>.pbtxt`` > summary ``title`` > first line of
  ``preview`` (``title`` is often empty).
- SQLite is always opened with ``mode="copy"`` (``mode=ro`` was suspected of leaving
  ``-wal``/``-shm`` next to the originals).
- Tokens: ``input_tokens`` / ``output_tokens`` / ``cache_read_tokens`` of each
  ``PLANNER_RESPONSE`` step, put on the first event emitted for that step. No cost.
- Tool results carry no name / id: they are paired in order with the calls of the
  preceding ``PLANNER_RESPONSE``; ``call_id`` is synthesized as ``<step_index>.<n>``.
- ``daemon/`` (``csrfToken``), ``installation_id``, ``log/``, ``presence/`` are never opened;
  secret-looking keys are dropped from ``Event.raw``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_logs.adapters.base import Adapter
from agent_logs.model import Event, Filters, Session, SourceInfo
from agent_logs.paths import home, list_dir, mtime, normalize_path, tool_root
from agent_logs.readers import dumps_compact, iter_jsonl, open_sqlite, text_of
from agent_logs.timeutil import parse_ts

ROOTS = ("antigravity", "antigravity-cli", "antigravity-ide")
_SUMMARY_COLS = (
    "conversation_id",
    "title",
    "preview",
    "step_count",
    "last_modified_time",
    "workspace_uris",
    "source",
    "parent_conversation_id",
    "agent_name",
    "last_user_input_time",
)
_SECRET_KEYS = {"csrftoken", "csrf_token", "installation_id", "installationid"}
_SYSTEM_TYPES = {
    "SYSTEM_MESSAGE",
    "EPHEMERAL_MESSAGE",
    "KNOWLEDGE_ARTIFACTS",
    "ERROR_MESSAGE",
}
_SUMMARY_TYPES = {"CHECKPOINT", "CONVERSATION_HISTORY"}
_TITLE_RE = re.compile(r'title:\s*"((?:[^"\\]|\\.)*)"')


@dataclass
class _Cand:
    """One conversation as seen in one root."""

    id: str
    root: str
    transcript: Path | None = None
    transcript_mtime: datetime | None = None
    summary: dict[str, Any] | None = None
    summary_db: Path | None = None
    annotation: Path | None = None

    @property
    def summary_time(self) -> datetime | None:
        return parse_ts((self.summary or {}).get("last_modified_time"))


@dataclass
class _Conv:
    id: str
    primary: _Cand
    others: list[_Cand] = field(default_factory=list)


class AntigravityAdapter(Adapter):
    name = "antigravity"
    env_var = "AGENT_LOGS_ANTIGRAVITY_DIR"

    def base(self) -> Path:
        return tool_root(self.name, home() / ".gemini")

    # ------------------------------------------------------------ discovery

    def _transcript(self, brain_dir: Path) -> Path | None:
        logs = brain_dir / ".system_generated" / "logs"
        for name in ("transcript_full.jsonl", "transcript.jsonl"):
            p = logs / name
            if p.is_file():
                return p
        return None

    def _summaries(self, db: Path) -> list[dict[str, Any]]:
        if not db.is_file():
            return []
        try:
            with open_sqlite(db, mode="copy") as conn:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(conversation_summaries)")}
                if "conversation_id" not in cols:
                    self.warn(f"{db}: no conversation_summaries table")
                    return []
                sel = ", ".join(c for c in _SUMMARY_COLS if c in cols)
                rows = conn.execute(f"SELECT {sel} FROM conversation_summaries").fetchall()
                return [dict(r) for r in rows if r["conversation_id"]]
        except Exception as exc:  # noqa: BLE001 - sqlite / OS errors per file
            self.warn(f"{db}: {type(exc).__name__}: {exc}")
            return []

    def _scan_root(self, root_name: str) -> dict[str, _Cand]:
        root = self.base() / root_name
        cands: dict[str, _Cand] = {}
        db = root / "conversation_summaries.db"
        for row in self._summaries(db):
            cid = str(row["conversation_id"])
            cands[cid] = _Cand(cid, root_name, summary=row, summary_db=db)
        for d in list_dir(root / "brain"):
            if not d.is_dir():
                continue
            t = self._transcript(d)
            if t is None:
                continue
            c = cands.setdefault(d.name, _Cand(d.name, root_name))
            c.transcript, c.transcript_mtime = t, mtime(t)
        ann_dir = root / "annotations"
        if ann_dir.is_dir():
            for cid, c in cands.items():
                a = ann_dir / f"{cid}.pbtxt"
                if a.is_file():
                    c.annotation = a
        return cands

    def _conversations(self) -> list[_Conv]:
        by_id: dict[str, list[_Cand]] = {}
        for r in ROOTS:
            for cid, c in self._scan_root(r).items():
                by_id.setdefault(cid, []).append(c)
        out = []
        for cid, cs in by_id.items():
            with_t = [c for c in cs if c.transcript]
            if with_t:
                primary = max(with_t, key=lambda c: _key(c.transcript_mtime))
            else:
                primary = max(cs, key=lambda c: _key(c.summary_time))
            out.append(_Conv(cid, primary, [c for c in cs if c is not primary]))
        return out

    def detect(self) -> list[SourceInfo]:
        out: list[SourceInfo] = []
        base = self.base()
        for r in ROOTS:
            root = base / r
            db = root / "conversation_summaries.db"
            rows = self._summaries(db) if db.is_file() else []
            out.append(
                SourceInfo(
                    self.name,
                    f"{r}/summaries",
                    str(db),
                    db.is_file(),
                    len(rows) if db.is_file() else None,
                    mtime(db),
                    note=f"metadata index; base via {self.env_var} / ~/.gemini",
                )
            )
            brain = root / "brain"
            ts = [t for t in (self._transcript(d) for d in list_dir(brain) if d.is_dir()) if t]
            out.append(
                SourceInfo(
                    self.name,
                    f"{r}/transcripts",
                    str(brain),
                    brain.is_dir(),
                    len(ts),
                    max((m for m in (mtime(t) for t in ts) if m), default=None),
                    note="brain/<id>/.system_generated/logs/transcript[_full].jsonl (event source)",
                )
            )
            conv = root / "conversations"
            dbs = [p for p in list_dir(conv) if p.is_file() and p.name.endswith(".db")]
            out.append(
                SourceInfo(
                    self.name,
                    f"{r}/conversations",
                    str(conv),
                    conv.is_dir(),
                    len(dbs),
                    max((m for m in (mtime(p) for p in dbs) if m), default=None),
                    note="per-conversation protobuf DBs; not decoded in v1",
                )
            )
        return out

    # ------------------------------------------------------------ sessions

    def iter_sessions(self, filters: Filters) -> Iterator[Session]:
        for conv in self._conversations():
            p = conv.primary
            if filters.since:
                latest = max(
                    (
                        t
                        for t in (
                            p.transcript_mtime,
                            p.summary_time,
                            *(o.summary_time for o in conv.others),
                        )
                        if t
                    ),
                    default=None,
                )
                if latest and latest < filters.since:
                    continue
            s = self._session(conv)
            if s is not None:
                yield s

    def _session(self, conv: _Conv) -> Session | None:
        p = conv.primary
        cands = [p, *conv.others]
        summ_c = next((c for c in cands if c.summary), None)
        if p.summary is None and summ_c is not None:
            # newest summary among the other roots
            summ_c = max((c for c in cands if c.summary), key=lambda c: _key(c.summary_time))
        summary = p.summary or (summ_c.summary if summ_c else None) or {}
        s = Session(id=conv.id, tool=self.name, source=p.root)
        uris = _json_list(summary.get("workspace_uris"))
        if uris:
            s.cwd = str(uris[0])
            s.project = normalize_path(s.cwd)
        s.parent_id = summary.get("parent_conversation_id") or None
        title = None
        for c in cands:
            if c.annotation:
                title = _annotation_title(c.annotation)
                if title:
                    break
        s.title = title or summary.get("title") or _first_line(summary.get("preview")) or None
        s.ended_at = parse_ts(summary.get("last_modified_time"))
        if p.transcript is None:
            s.path = str(p.summary_db) if p.summary_db else None
            s.ref = None
            return s
        s.path = str(p.transcript)
        s.ref = p.transcript
        msgs = calls = 0
        tok: dict[str, int | None] = dict.fromkeys(("tokens_in", "tokens_out", "tokens_cache_read"))
        try:
            for ev in self._walk(p.transcript, conv.id):
                if ev.ts:
                    if s.started_at is None or ev.ts < s.started_at:
                        s.started_at = ev.ts
                    if s.ended_at is None or ev.ts > s.ended_at:
                        s.ended_at = ev.ts
                if ev.kind == "message" and ev.role in ("user", "assistant"):
                    msgs += 1
                elif ev.kind == "tool_call":
                    calls += 1
                if ev.model:
                    s.model = ev.model
                for k in tok:
                    v = getattr(ev, k)
                    if v is not None:
                        tok[k] = (tok[k] or 0) + v
        except OSError as exc:
            self.warn(f"{p.transcript}: {exc}")
            return s
        s.message_count, s.tool_call_count = msgs, calls
        for k, v in tok.items():
            setattr(s, k, v)
        return s

    # ------------------------------------------------------------ events

    def iter_events(self, session: Session) -> Iterator[Event]:
        path = session.ref if isinstance(session.ref, Path) else None
        if path is None:
            return  # metadata-only conversation (summary DB); protobuf DB not decoded
        yield from self._walk(path, session.id)

    def _walk(self, path: Path, sid: str) -> Iterator[Event]:
        pending: list[tuple[str | None, str]] = []  # (tool name, synthesized call id)
        for rec in iter_jsonl(path):
            t = str(rec.get("type") or "")
            src = rec.get("source")
            ts = parse_ts(rec.get("created_at"))
            raw = _scrub(rec)
            base = dict(session_id=sid, tool=self.name, ts=ts, raw=raw)
            content = text_of(rec.get("content"))
            if t == "USER_INPUT":
                yield Event(role="user", kind="message", text=content, **base)
            elif t == "PLANNER_RESPONSE":
                yield from self._planner(rec, base, content, pending)
            elif t in _SUMMARY_TYPES:
                yield Event(role="system", kind="summary", text=content or t, **base)
            elif t in _SYSTEM_TYPES or src in ("SYSTEM", "SYSTEM_SDK"):
                text = content or text_of(rec.get("error")) or t
                yield Event(role="system", kind="system", text=text, **base)
            elif t and src in ("MODEL", "USER_EXPLICIT"):
                name, cid = pending.pop(0) if pending and src == "MODEL" else (None, None)
                text = content or text_of(rec.get("error"))
                yield Event(
                    role="tool",
                    kind="tool_result",
                    tool_name=name or t.lower(),
                    call_id=cid,
                    text=text,
                    **base,
                )
            else:
                yield Event(role=None, kind="raw", text=content, **base)

    def _planner(self, rec, base, content, pending) -> Iterator[Event]:
        model = rec.get("model") or None
        events: list[Event] = []
        a = dict(role="assistant", model=model, **base)
        if rec.get("thinking"):
            events.append(Event(kind="reasoning", text=text_of(rec["thinking"]), **a))
        if content:
            events.append(Event(kind="message", text=content, **a))
        calls = rec.get("tool_calls") if isinstance(rec.get("tool_calls"), list) else []
        if calls:
            pending.clear()
        idx = rec.get("step_index")
        for n, c in enumerate(calls):
            if not isinstance(c, dict):
                continue
            cid = f"{idx}.{n}" if idx is not None else None
            name = c.get("name")
            pending.append((name, cid))
            args = c.get("args")
            events.append(
                Event(
                    kind="tool_call",
                    tool_name=name,
                    call_id=cid,
                    text=dumps_compact(args) if args is not None else None,
                    **a,
                )
            )
        tin, tout = _int(rec.get("input_tokens")), _int(rec.get("output_tokens"))
        tcache = _int(rec.get("cache_read_tokens"))
        if not events and (tin is not None or tout is not None or tcache is not None):
            events.append(Event(kind="usage", text=None, **a))
        if events:
            e = events[0]
            e.tokens_in, e.tokens_out, e.tokens_cache_read = tin, tout, tcache
        yield from events


# ---------------------------------------------------------------- helpers


def _key(dt: datetime | None) -> float:
    return dt.timestamp() if dt else float("-inf")


def _int(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if not value or not isinstance(value, str):
        return []
    try:
        v = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [x for x in v if x] if isinstance(v, list) else []


def _first_line(value: Any, limit: int = 100) -> str | None:
    if not isinstance(value, str):
        return None
    line = next((ln.strip() for ln in value.splitlines() if ln.strip()), "")
    return line[:limit] or None


def _scrub(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in rec.items() if k.lower() not in _SECRET_KEYS}


def _annotation_title(path: Path) -> str | None:
    """First ``title:"..."`` of a protobuf text file (C-style escapes, UTF-8 octal bytes)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _TITLE_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    if "\\" not in raw:
        return raw or None
    try:
        out = raw.encode("latin-1").decode("unicode_escape").encode("latin-1").decode("utf-8")
    except (UnicodeError, ValueError):
        out = raw.replace('\\"', '"').replace("\\\\", "\\")
    return out or None
