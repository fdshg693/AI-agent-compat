"""Claude Code: ``~/.claude/projects/<enc-cwd>/<sessionId>.jsonl`` (+ subagents).

Spec: skills/plugins/cc-knowledge/skills/claude-logs-investigate/log-format.md

- Root: ``AGENT_LOGS_CLAUDE_DIR`` > ``CLAUDE_CONFIG_DIR`` > ``~/.claude``.
- Main sessions are the direct ``*.jsonl`` children of each project dir (``*.orphaned-*``
  is skipped). Subagents (``<sid>/subagents/**/agent-<id>.jsonl``) become their own
  sessions with ``source="subagent"`` and ``parent_id=<sid>``.
- Project is the first recorded ``cwd`` (the directory name is lossy).
- One API response is split across several ``assistant`` lines sharing ``message.id``;
  usage is counted once per id (the last value seen). Session cost comes from the
  last ``cost-state`` (cumulative); subagent sessions have no cost.
- ``api-request*`` lines are dropped before parsing; ``session-owner`` and other
  metadata records are never emitted. ``~/.claude/.credentials.json`` is never opened.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agent_logs.adapters.base import Adapter
from agent_logs.model import Event, Filters, Session, SourceInfo
from agent_logs.paths import home, list_dir, mtime, normalize_path, walk_files
from agent_logs.readers import dumps_compact, iter_jsonl, read_json, text_of
from agent_logs.timeutil import parse_ts

_SKIP_LINES = ('"type":"api-request',)
# Known records that are metadata or may hold identifiers/secrets: never emitted.
_IGNORED = {
    "session-owner",
    "attachment",
    "queue-operation",
    "last-prompt",
    "ai-title",
    "custom-title",
    "file-history-snapshot",
    "file-history-delta",
    "tools-used",
    "atis-latch",
    "mode",
    "permission-mode",
    "pr-link",
    "api-request",
    "api-request-shape",
    "api-request-blob",
    "progress",
}


class ClaudeAdapter(Adapter):
    name = "claude"
    env_var = "AGENT_LOGS_CLAUDE_DIR"

    def root(self) -> Path:
        env = os.environ.get(self.env_var)
        if env:
            return Path(env)
        if os.environ.get("CLAUDE_CONFIG_DIR") and not os.environ.get("AGENT_LOGS_HOME"):
            return Path(os.environ["CLAUDE_CONFIG_DIR"])
        return home() / ".claude"

    # ------------------------------------------------------------ discovery

    def _main_files(self) -> Iterator[Path]:
        for proj in list_dir(self.root() / "projects"):
            if not proj.is_dir():
                continue
            for f in list_dir(proj):
                if f.is_file() and f.name.endswith(".jsonl") and ".orphaned-" not in f.name:
                    yield f

    def detect(self) -> list[SourceInfo]:
        root = self.root()
        projects = root / "projects"
        files = list(self._main_files())
        last = max((m for m in (mtime(f) for f in files) if m), default=None)
        out = [
            SourceInfo(
                self.name,
                "projects",
                str(projects),
                projects.is_dir(),
                len(files),
                last,
                note=f"root via {self.env_var} / CLAUDE_CONFIG_DIR / ~/.claude",
            )
        ]
        hist = root / "history.jsonl"
        out.append(
            SourceInfo(
                self.name,
                "history",
                str(hist),
                hist.is_file(),
                None,
                mtime(hist),
                note="prompt history only; not read",
            )
        )
        return out

    def iter_sessions(self, filters: Filters) -> Iterator[Session]:
        for f in self._main_files():
            if filters.since:
                m = mtime(f)
                if m and m < filters.since:
                    continue
            s = self._summarize(f, Session(id=f.stem, tool=self.name, source="main"))
            if s:
                yield s
            sub_dir = f.with_suffix("") / "subagents"
            for sf in walk_files(sub_dir, suffixes=(".jsonl",)):
                if not sf.name.startswith("agent-"):
                    continue  # journal.jsonl etc.
                if filters.since:
                    m = mtime(sf)
                    if m and m < filters.since:
                        continue
                meta = read_json(sf.with_name(sf.stem + ".meta.json")) or {}
                sub = Session(
                    id=sf.stem[len("agent-") :],
                    tool=self.name,
                    source="workflow" if "workflows" in sf.parts else "subagent",
                    parent_id=f.stem,
                    title=meta.get("description") if isinstance(meta, dict) else None,
                    model=meta.get("model") if isinstance(meta, dict) else None,
                )
                s2 = self._summarize(sf, sub)
                if s2:
                    yield s2

    def _summarize(self, path: Path, s: Session) -> Session | None:
        s.path = str(path)
        s.ref = path
        msgs = calls = 0
        tok: dict[str, int | None] = dict.fromkeys(
            ("tokens_in", "tokens_out", "tokens_cache_read", "tokens_cache_write")
        )
        ai_title = custom_title = None
        try:
            for rec, ev in self._walk(path):
                t = rec.get("type")
                if t == "ai-title":
                    ai_title = rec.get("aiTitle") or ai_title
                elif t == "custom-title":
                    custom_title = rec.get("customTitle") or custom_title
                elif t == "cost-state" and s.source == "main":
                    if isinstance(rec.get("totalCostUSD"), (int, float)):
                        s.cost = float(rec["totalCostUSD"])
                if s.cwd is None and rec.get("cwd") and t in ("user", "attachment", "assistant"):
                    s.cwd = rec["cwd"]
                ts = parse_ts(rec.get("timestamp"))
                if ts:
                    s.started_at = ts if s.started_at is None or ts < s.started_at else s.started_at
                    s.ended_at = ts if s.ended_at is None or ts > s.ended_at else s.ended_at
                if ev is None:
                    continue
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
            self.warn(f"{path}: {exc}")
            return None
        s.title = custom_title or ai_title or s.title
        s.project = normalize_path(s.cwd)
        s.message_count, s.tool_call_count = msgs, calls
        for k, v in tok.items():
            setattr(s, k, v)
        return s

    # ------------------------------------------------------------ events

    def iter_events(self, session: Session) -> Iterator[Event]:
        path = session.ref if isinstance(session.ref, Path) else Path(session.path or "")
        for _rec, ev in self._walk(path, session_id=session.id):
            if ev is not None:
                yield ev

    def _walk(
        self, path: Path, session_id: str | None = None
    ) -> Iterator[tuple[dict[str, Any], Event | None]]:
        """Yield ``(record, event-or-None)``. Assistant events of one ``message.id`` are
        buffered so its usage lands once, on the first event of that response."""
        sid = session_id or path.stem.removeprefix("agent-")
        tool_names: dict[str, str] = {}
        counted: set[str] = set()
        buf: list[tuple[dict, Event]] = []
        buf_id: str | None = None
        buf_usage: dict | None = None

        def flush() -> Iterator[tuple[dict, Event | None]]:
            nonlocal buf, buf_id, buf_usage
            if buf and buf_id and buf_id not in counted and isinstance(buf_usage, dict):
                counted.add(buf_id)
                e = buf[0][1]
                e.tokens_in = _int(buf_usage.get("input_tokens"))
                e.tokens_out = _int(buf_usage.get("output_tokens"))
                e.tokens_cache_read = _int(buf_usage.get("cache_read_input_tokens"))
                e.tokens_cache_write = _int(buf_usage.get("cache_creation_input_tokens"))
            yield from buf
            buf, buf_id, buf_usage = [], None, None

        for rec in iter_jsonl(path, skip_if_contains=_SKIP_LINES):
            t = rec.get("type")
            msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
            if t == "assistant":
                mid = msg.get("id") or rec.get("requestId") or rec.get("uuid")
                if mid != buf_id:
                    yield from flush()
                    buf_id = mid
                if isinstance(msg.get("usage"), dict):
                    buf_usage = msg["usage"]
                events = list(self._assistant_events(rec, msg, sid, tool_names))
                if not events:
                    yield rec, None
                for e in events:
                    buf.append((rec, e))
                continue
            yield from flush()
            if t in _IGNORED:
                yield rec, None
                continue
            events = list(self._other_events(rec, t, msg, sid, tool_names))
            if not events:
                yield rec, None
            for e in events:
                yield rec, e
        yield from flush()

    def _assistant_events(self, rec, msg, sid, tool_names) -> Iterator[Event]:
        ts = parse_ts(rec.get("timestamp"))
        model = msg.get("model")
        if model == "<synthetic>":
            model = None
        content = msg.get("content")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            base = dict(
                session_id=sid, tool=self.name, ts=ts, role="assistant", model=model, raw=rec
            )
            if bt == "text":
                yield Event(kind="message", text=text_of(b.get("text")), **base)
            elif bt in ("thinking", "redacted_thinking"):
                yield Event(kind="reasoning", text=text_of(b.get("thinking")), **base)
            elif bt in ("tool_use", "server_tool_use"):
                if b.get("id") and b.get("name"):
                    tool_names[b["id"]] = b["name"]
                yield Event(
                    kind="tool_call",
                    tool_name=b.get("name"),
                    call_id=b.get("id"),
                    text=dumps_compact(b.get("input")) if b.get("input") is not None else None,
                    **base,
                )

    def _other_events(self, rec, t, msg, sid, tool_names) -> Iterator[Event]:
        ts = parse_ts(rec.get("timestamp"))
        base = dict(session_id=sid, tool=self.name, ts=ts, raw=rec)
        if t == "user":
            content = msg.get("content")
            meta = bool(rec.get("isMeta"))
            if isinstance(content, str):
                yield Event(
                    role="system" if meta else "user",
                    kind="system" if meta else "message",
                    text=content,
                    **base,
                )
                return
            for b in content if isinstance(content, list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    yield Event(
                        role="system" if meta else "user",
                        kind="system" if meta else "message",
                        text=b.get("text"),
                        **base,
                    )
                elif b.get("type") == "tool_result":
                    cid = b.get("tool_use_id")
                    yield Event(
                        role="tool",
                        kind="tool_result",
                        call_id=cid,
                        tool_name=tool_names.get(cid),
                        text=text_of(b.get("content")),
                        **base,
                    )
        elif t == "system":
            sub = rec.get("subtype")
            if sub == "turn_duration":
                yield Event(role="system", kind="turn_end", text=None, **base)
            elif sub == "compact_boundary":
                yield Event(role="system", kind="summary", text="compact boundary", **base)
            else:
                yield Event(
                    role="system", kind="system", text=text_of(rec.get("content")) or sub, **base
                )
        elif t == "summary":
            yield Event(role="system", kind="summary", text=text_of(rec.get("summary")), **base)
        elif t == "cost-state":
            cost = rec.get("totalCostUSD")
            yield Event(
                role=None,
                kind="usage",
                text="cost-state (cumulative)",
                cost=float(cost) if isinstance(cost, (int, float)) else None,
                **base,
            )
        elif t:
            yield Event(role=None, kind="raw", text=None, **base)


def _int(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
