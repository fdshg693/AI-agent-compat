"""OpenAI Codex: ``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`` (+ ``archived_sessions/``).

Spec: skills/plugins/ai-tools-knowledge/skills/codex-logs/SKILL.md

- Root: ``AGENT_LOGS_CODEX_DIR`` > ``CODEX_HOME`` (ignored when ``AGENT_LOGS_HOME`` is set)
  > ``~/.codex``. ``state_5.sqlite`` lives under ``CODEX_SQLITE_HOME`` when that is set
  (same rule), else the root. ``config.toml``'s ``sqlite_home`` is not read.
- Rollouts are the body. ``state_5.sqlite`` (``threads``) and ``session_index.jsonl`` only
  fill title / cwd / model. Title: session_index ``thread_name`` > ``threads.name`` >
  ``threads.title`` > first user message.
- Session id is ``session_meta.payload.id`` (fallback: the UUID in the file name). A revert
  rollout (``...-<thread>_<rollout>.jsonl``) gets ``<thread>_<rollout>`` so ids stay unique.
- ``.jsonl.zst`` (rollouts older than 7 days) is read with ``compression.zstd`` on Python
  3.14+; below that it is skipped, counted in ``detect()`` and warned about once.
- Legacy mode records each utterance twice; the ``response_item`` side is used and
  ``event_msg.user_message`` / ``agent_message`` / ``agent_reasoning*`` are dropped.
  Other ``event_msg`` duplicates of tool results (``*_end``, ``item_completed``) become raw.
- Tokens: when the rollout has ``token_usage_record`` lines those carry per-response usage
  and the session total is the last ``thread_token_usage``; otherwise ``event_msg.token_count``
  is cumulative: the session total is the last ``total_token_usage`` and each usage event
  carries the delta to the previous total (repeated / null rows emit nothing).
  ``tokens_in`` = ``input_tokens - cached_input_tokens`` (OpenAI counts cached input inside
  ``input_tokens``), ``tokens_cache_read`` = ``cached_input_tokens``. No cost is recorded.
- ``session_meta`` / ``turn_context`` are metadata and never emitted (``base_instructions``).
  ``auth.json`` is never opened.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agent_logs.adapters.base import Adapter
from agent_logs.model import Event, Filters, Session, SourceInfo
from agent_logs.paths import home, list_dir, mtime, normalize_path, walk_files
from agent_logs.readers import dumps_compact, iter_jsonl, open_sqlite, table_names
from agent_logs.timeutil import parse_ts

try:  # Python 3.14+
    from compression import zstd as _zstd  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depends on the interpreter
    _zstd = None

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_NAME = re.compile(rf"^rollout-.*?(?P<thread>{_UUID})(?:_(?P<rollout>{_UUID}))?\.jsonl(?:\.zst)?$")
# legacy-mode duplicates of response_item content
_DUPLICATE_EVENTS = {
    "user_message",
    "agent_message",
    "agent_reasoning",
    "agent_reasoning_raw_content",
    "agent_reasoning_section_break",
}
# user messages injected by Codex itself (AGENTS.md, environment, ...); inferred tags
_INJECTED_PREFIXES = (
    "<environment_context",
    "<user_instructions",
    "<permissions instructions",
    "<user_shell_command",
    "# AGENTS.md instructions",
)
_TOKEN_KEYS = ("tokens_in", "tokens_out", "tokens_cache_read", "tokens_cache_write")


class CodexAdapter(Adapter):
    name = "codex"
    env_var = "AGENT_LOGS_CODEX_DIR"

    def __init__(self) -> None:
        super().__init__()
        self._zst_warned = False

    def root(self) -> Path:
        env = os.environ.get(self.env_var)
        if env:
            return Path(env)
        if os.environ.get("CODEX_HOME") and not os.environ.get("AGENT_LOGS_HOME"):
            return Path(os.environ["CODEX_HOME"])
        return home() / ".codex"

    def state_db(self) -> Path:
        if (
            os.environ.get("CODEX_SQLITE_HOME")
            and not os.environ.get("AGENT_LOGS_HOME")
            and not os.environ.get(self.env_var)
        ):
            return Path(os.environ["CODEX_SQLITE_HOME"]) / "state_5.sqlite"
        return self.root() / "state_5.sqlite"

    # ------------------------------------------------------------ discovery

    def _rollouts(self) -> Iterator[tuple[Path, str]]:
        """``(path, source)`` for every rollout; ``.zst`` only when no plain twin exists."""
        root = self.root()
        groups = (
            ("sessions", list(walk_files(root / "sessions"))),
            ("archived", [p for p in list_dir(root / "archived_sessions") if p.is_file()]),
        )
        for source, files in groups:
            names = {p.name for p in files}
            for p in sorted(files):
                if not _NAME.match(p.name):
                    continue  # .tmp / .pending / staged files, other junk
                if p.name.endswith(".zst") and p.name[: -len(".zst")] in names:
                    continue
                yield p, source

    def detect(self) -> list[SourceInfo]:
        root = self.root()
        all_files = list(self._rollouts())
        out = []
        for source, sub in (("sessions", "sessions"), ("archived", "archived_sessions")):
            files = [p for p, s in all_files if s == source]
            zst = sum(1 for p in files if p.name.endswith(".zst"))
            last = max((m for m in (mtime(f) for f in files) if m), default=None)
            note = "root via AGENT_LOGS_CODEX_DIR / CODEX_HOME / ~/.codex"
            if zst and _zstd is None:
                note += f"; {zst} .jsonl.zst skipped (needs Python 3.14+)"
            elif zst:
                note += f"; {zst} .jsonl.zst"
            path = root / sub
            out.append(
                SourceInfo(
                    self.name,
                    source,
                    str(path),
                    path.is_dir(),
                    len(files) - (zst if _zstd is None else 0),
                    last,
                    note=note,
                )
            )
        db = self.state_db()
        out.append(
            SourceInfo(
                self.name,
                "state",
                str(db),
                db.is_file(),
                None,
                mtime(db),
                note="threads index; metadata only",
            )
        )
        idx = root / "session_index.jsonl"
        out.append(
            SourceInfo(
                self.name,
                "session_index",
                str(idx),
                idx.is_file(),
                None,
                mtime(idx),
                note="thread names; metadata only",
            )
        )
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

    def _load_threads(self) -> dict[str, dict[str, Any]]:
        db = self.state_db()
        if not db.is_file():
            return {}
        try:
            with open_sqlite(db, mode="ro") as conn:
                if "threads" not in table_names(conn):
                    return {}
                cols = {r[1] for r in conn.execute("PRAGMA table_info(threads)")}
                want = [c for c in ("id", "name", "title", "cwd", "model") if c in cols]
                if "id" not in want:
                    return {}
                rows = conn.execute(f"SELECT {', '.join(want)} FROM threads").fetchall()
                return {str(r["id"]): dict(r) for r in rows}
        except (sqlite3.Error, OSError) as exc:
            self.warn(f"{db}: {exc}")
            return {}

    def _load_index(self) -> dict[str, str]:
        idx = self.root() / "session_index.jsonl"
        names: dict[str, str] = {}
        if not idx.is_file():
            return names
        try:
            for rec in iter_jsonl(idx):
                if rec.get("id") and rec.get("thread_name"):
                    names[str(rec["id"])] = str(rec["thread_name"])  # last line wins
        except OSError as exc:
            self.warn(f"{idx}: {exc}")
        return names

    def iter_sessions(self, filters: Filters) -> Iterator[Session]:
        threads = self._load_threads()
        index = self._load_index()
        skipped = 0
        seen: set[str] = set()
        for path, source in self._rollouts():
            if path.name.endswith(".zst") and _zstd is None:
                skipped += 1
                continue
            if filters.since:
                m = mtime(path)
                if m and m < filters.since:
                    continue
            s = self._summarize(path, source, threads, index)
            if s is None or s.id in seen:
                continue
            seen.add(s.id)
            yield s
        if skipped and not self._zst_warned:
            self._zst_warned = True
            self.warn(
                f"{skipped} compressed rollout(s) (.jsonl.zst) skipped: "
                "reading zstd needs Python 3.14+"
            )

    def _summarize(self, path: Path, source: str, threads: dict, index: dict) -> Session | None:
        m = _NAME.match(path.name)
        s = Session(
            id=m.group("thread") if m else path.stem,
            tool=self.name,
            source=source,
            path=str(path),
            ref=path,
        )
        st = _State()
        msgs = calls = 0
        first_user: str | None = None
        try:
            for rec, ev in self._walk(path, st, session_id=s.id):
                ts = parse_ts(rec.get("timestamp"))
                if ts:
                    s.started_at = ts if s.started_at is None or ts < s.started_at else s.started_at
                    s.ended_at = ts if s.ended_at is None or ts > s.ended_at else s.ended_at
                if ev is None:
                    continue
                if ev.kind == "message" and ev.role in ("user", "assistant"):
                    msgs += 1
                    if ev.role == "user" and first_user is None and ev.text:
                        first_user = ev.text
                elif ev.kind == "tool_call":
                    calls += 1
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the listing
            self.warn(f"{path}: {type(exc).__name__}: {exc}")
            return None
        meta = st.meta
        if meta.get("id"):
            s.id = str(meta["id"])
        if m and m.group("rollout"):
            s.id = f"{s.id}_{m.group('rollout')}"
        thread_id = s.id.split("_", 1)[0]
        row = threads.get(thread_id, {})
        s.cwd = meta.get("cwd") or st.first_turn_cwd or row.get("cwd")
        s.project = normalize_path(s.cwd)
        s.model = st.model or row.get("model")
        meta_ts = parse_ts(meta.get("timestamp"))
        if meta_ts:
            s.started_at = meta_ts
        s.parent_id = _parent_of(meta)
        title = index.get(thread_id) or row.get("name") or row.get("title")
        if not title and first_user:
            title = first_user.strip().splitlines()[0][:80] if first_user.strip() else None
        s.title = title
        s.message_count, s.tool_call_count = msgs, calls
        for k, v in st.totals().items():
            setattr(s, k, v)
        return s

    # ------------------------------------------------------------ events

    def iter_events(self, session: Session) -> Iterator[Event]:
        path = session.ref if isinstance(session.ref, Path) else Path(session.path or "")
        if path.name.endswith(".zst") and _zstd is None:
            self.warn(f"{path}: reading .jsonl.zst needs Python 3.14+")
            return
        for _rec, ev in self._walk(path, _State(), session_id=session.id):
            if ev is not None:
                yield ev

    def _records(self, path: Path) -> Iterator[dict[str, Any]]:
        if path.name.endswith(".zst"):
            yield from _iter_zst(path)
            return
        try:
            yield from iter_jsonl(path)
        except FileNotFoundError:
            # the compression worker may have replaced it while we were scanning
            zst = path.with_name(path.name + ".zst")
            if _zstd is None or not zst.is_file():
                raise
            yield from _iter_zst(zst)

    def _has_usage_records(self, path: Path) -> bool:
        if path.name.endswith(".zst"):
            return any(r.get("type") == "token_usage_record" for r in _iter_zst(path))
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"token_usage_record"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(rec, dict) and rec.get("type") == "token_usage_record":
                        return True
        except FileNotFoundError:
            return False
        return False

    def _walk(
        self, path: Path, st: _State, session_id: str
    ) -> Iterator[tuple[dict[str, Any], Event | None]]:
        st.record_mode = self._has_usage_records(path)
        tool_names: dict[str, str] = {}
        for rec in self._records(path):
            payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
            t = rec.get("type")
            ts = parse_ts(rec.get("timestamp"))
            base = dict(session_id=session_id, tool=self.name, ts=ts, raw=rec)
            if t == "session_meta":
                if not st.meta:
                    st.meta = payload
                yield rec, None
            elif t == "turn_context":
                if payload.get("model"):
                    st.model = str(payload["model"])
                if st.first_turn_cwd is None and payload.get("cwd"):
                    st.first_turn_cwd = payload["cwd"]
                yield rec, None
            elif t == "response_item":
                ev = self._response_item(payload, base, st, tool_names)
                yield rec, ev
            elif t == "event_msg":
                yield rec, self._event_msg(payload, base, st)
            elif t == "token_usage_record":
                usage = _usage(payload.get("usage"))
                thread_total = _usage(payload.get("thread_token_usage"))
                if thread_total is not None:
                    st.record_total = thread_total
                elif usage is not None:
                    acc = st.record_sum or dict.fromkeys(_TOKEN_KEYS)
                    st.record_sum = {k: _add(acc[k], usage[k]) for k in _TOKEN_KEYS}
                yield (
                    rec,
                    Event(
                        role=None,
                        kind="usage",
                        text="token_usage_record",
                        model=st.model,
                        **(usage or {}),
                        **base,
                    ),
                )
            elif t == "compacted":
                text = payload.get("message")
                yield (
                    rec,
                    Event(
                        role="system",
                        kind="summary",
                        text=str(text) if text else "compacted",
                        **base,
                    ),
                )
            elif t:
                yield rec, Event(role=None, kind="raw", text=None, **base)
            else:
                yield rec, None

    def _response_item(self, p: dict, base: dict, st: _State, tool_names: dict) -> Event:
        pt = p.get("type")
        if pt == "message":
            role = p.get("role")
            text = _content_text(p.get("content"))
            if role in ("developer", "system"):
                return Event(role="system", kind="system", text=text, **base)
            if role == "user":
                if text and text.lstrip().startswith(_INJECTED_PREFIXES):
                    return Event(role="system", kind="system", text=text, **base)
                return Event(role="user", kind="message", text=text, **base)
            if role == "assistant":
                return Event(role="assistant", kind="message", text=text, model=st.model, **base)
            return Event(role=None, kind="raw", text=text, **base)
        if pt == "reasoning":
            text = "\n".join(
                str(b.get("text"))
                for b in p.get("summary") or []
                if isinstance(b, dict) and b.get("text")
            ) or _content_text(p.get("content"))
            return Event(
                role="assistant", kind="reasoning", text=text or None, model=st.model, **base
            )
        if pt in (
            "function_call",
            "custom_tool_call",
            "local_shell_call",
            "tool_search_call",
            "web_search_call",
        ):
            name = p.get("name") or {
                "local_shell_call": "local_shell",
                "tool_search_call": "tool_search",
                "web_search_call": "web_search",
            }.get(pt)
            cid = p.get("call_id") or p.get("id")
            if cid and name:
                tool_names[cid] = name
            if pt == "function_call":
                text = _json_text(p.get("arguments"))
            elif pt == "custom_tool_call":
                text = _json_text(p.get("input"))
            else:
                arg = p.get("action") if p.get("action") is not None else p.get("arguments")
                text = dumps_compact(arg) if arg is not None else None
            return Event(
                role="assistant",
                kind="tool_call",
                tool_name=name,
                call_id=cid,
                text=text,
                model=st.model,
                **base,
            )
        if pt in ("function_call_output", "custom_tool_call_output", "tool_search_output"):
            cid = p.get("call_id")
            return Event(
                role="tool",
                kind="tool_result",
                call_id=cid,
                tool_name=tool_names.get(cid),
                text=_output_text(p.get("output")),
                **base,
            )
        return Event(role=None, kind="raw", text=None, **base)

    def _event_msg(self, p: dict, base: dict, st: _State) -> Event | None:
        et = p.get("type")
        if et in _DUPLICATE_EVENTS:
            return None
        if et == "token_count":
            info = p.get("info")
            if not isinstance(info, dict):
                return None
            total = _usage(info.get("total_token_usage"))
            if total is None or total == st.count_total:
                return None  # repeated cumulative value
            prev = st.count_total
            st.count_total = total
            if st.record_mode:
                tokens = {}  # token_usage_record lines already carry these
            else:
                tokens = {k: _delta(total[k], prev[k] if prev else None) for k in _TOKEN_KEYS}
            return Event(
                role=None,
                kind="usage",
                text="token_count (cumulative)",
                model=st.model,
                **tokens,
                **base,
            )
        if et in ("task_complete", "turn_complete"):
            # last_agent_message repeats the final assistant message: not copied
            return Event(role="system", kind="turn_end", text=None, **base)
        if et == "turn_aborted":
            return Event(
                role="system",
                kind="system",
                text=f"turn aborted: {p.get('reason')}" if p.get("reason") else "turn aborted",
                **base,
            )
        return Event(role=None, kind="raw", text=None, **base)


class _State:
    """Per-rollout state shared between ``_walk`` and ``_summarize``."""

    def __init__(self) -> None:
        self.meta: dict[str, Any] = {}
        self.model: str | None = None
        self.first_turn_cwd: str | None = None
        self.record_mode = False
        self.count_total: dict[str, int | None] | None = None
        self.record_total: dict[str, int | None] | None = None
        self.record_sum: dict[str, int | None] | None = None

    def totals(self) -> dict[str, int | None]:
        if self.record_mode:
            chosen = self.record_total or self.record_sum or self.count_total
        else:
            chosen = self.count_total
        return dict(chosen) if chosen else dict.fromkeys(_TOKEN_KEYS)


# ------------------------------------------------------------ helpers


def _iter_zst(path: Path) -> Iterator[dict[str, Any]]:
    if _zstd is None:
        return
    with _zstd.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def _parent_of(meta: dict[str, Any]) -> str | None:
    if meta.get("parent_thread_id"):
        return str(meta["parent_thread_id"])
    src = meta.get("source")
    if isinstance(src, dict):
        spawn = (src.get("subagent") or {}) if isinstance(src.get("subagent"), dict) else {}
        spawn = spawn.get("thread_spawn") if isinstance(spawn.get("thread_spawn"), dict) else {}
        if spawn.get("parent_thread_id"):
            return str(spawn["parent_thread_id"])
    if meta.get("forked_from_id"):
        return str(meta["forked_from_id"])
    return None


def _int(v: Any) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _usage(u: Any) -> dict[str, int | None] | None:
    """Codex TokenUsage -> normalized token fields (``None`` when not a dict)."""
    if not isinstance(u, dict):
        return None
    inp = _int(u.get("input_tokens"))
    cached = _int(u.get("cached_input_tokens"))
    if inp is not None and cached is not None:
        inp = max(inp - cached, 0)
    return {
        "tokens_in": inp,
        "tokens_out": _int(u.get("output_tokens")),
        "tokens_cache_read": cached,
        "tokens_cache_write": _int(u.get("cache_write_input_tokens")),
    }


def _delta(cur: int | None, prev: int | None) -> int | None:
    if cur is None:
        return None
    return cur - prev if prev is not None and cur >= prev else cur


def _add(a: int | None, b: int | None) -> int | None:
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content or None
    if not isinstance(content, list):
        return None
    parts = [
        str(b["text"])
        for b in content
        if isinstance(b, dict) and isinstance(b.get("text"), str) and b["text"]
    ]
    return "\n".join(parts) or None


def _output_text(output: Any) -> str | None:
    if isinstance(output, dict):  # older {content, success} shape
        output = output.get("content", output)
    if isinstance(output, list):
        return _content_text(output)
    if output is None:
        return None
    return output if isinstance(output, str) else dumps_compact(output)


def _json_text(value: Any) -> str | None:
    """``arguments`` is a JSON string: re-serialize compactly when it parses."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return dumps_compact(json.loads(value))
        except json.JSONDecodeError:
            return value
    return dumps_compact(value)
