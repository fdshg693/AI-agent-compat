"""Aggregation over sessions (and events when grouping by tool-call name)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from agent_logs.adapters.base import Adapter
from agent_logs.model import Filters, Session
from agent_logs.query import iter_events, iter_sessions

GROUP_KEYS = ("tool", "project", "model", "day", "month", "source", "tool-name")
_TOKEN_FIELDS = ("tokens_in", "tokens_out", "tokens_cache_read", "tokens_cache_write")


@dataclass
class Bucket:
    key: str
    sessions: int = 0
    messages: int = 0
    tool_calls: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_cache_read: int | None = None
    tokens_cache_write: int | None = None
    cost: float | None = None
    _seen: set = field(default_factory=set, repr=False)

    def add_num(self, name: str, value: Any) -> None:
        if value is None:
            return
        cur = getattr(self, name)
        setattr(self, name, value if cur is None else cur + value)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        if d["cost"] is not None:
            d["cost"] = round(d["cost"], 6)
        return d


def _session_key(s: Session, by: str) -> str:
    if by == "tool":
        return s.tool
    if by == "source":
        return f"{s.tool}/{s.source or '-'}"
    if by == "project":
        return s.project or s.cwd or "(unknown)"
    if by == "model":
        return s.model or "(unknown)"
    ts = s.started_at or s.ended_at
    if ts is None:
        return "(unknown)"
    local = ts.astimezone()
    return local.strftime("%Y-%m-%d" if by == "day" else "%Y-%m")


def aggregate(adapters: list[Adapter], f: Filters, by: str) -> list[Bucket]:
    buckets: dict[str, Bucket] = {}

    def bucket(key: str) -> Bucket:
        return buckets.setdefault(key, Bucket(key))

    sessions: Iterable[Session] = iter_sessions(adapters, f)
    if by == "tool-name":
        by_name = {a.name: a for a in adapters}
        for s in sessions:
            for e in iter_events(by_name[s.tool], s, f):
                if e.kind != "tool_call":
                    continue
                b = bucket(f"{s.tool}:{e.tool_name or '(unknown)'}")
                b.tool_calls += 1
                if (s.tool, s.id) not in b._seen:
                    b._seen.add((s.tool, s.id))
                    b.sessions += 1
    else:
        for s in sessions:
            b = bucket(_session_key(s, by))
            b.sessions += 1
            b.messages += s.message_count or 0
            b.tool_calls += s.tool_call_count or 0
            for name in _TOKEN_FIELDS:
                b.add_num(name, getattr(s, name))
            b.add_num("cost", s.cost)
    return sorted(buckets.values(), key=lambda b: (-b.sessions, -b.tool_calls, b.key))


def totals(buckets: list[Bucket]) -> Bucket:
    t = Bucket("TOTAL")
    for b in buckets:
        t.sessions += b.sessions
        t._seen |= b._seen
    if t._seen:  # tool-name grouping: a session using several tools counts once
        t.sessions = len(t._seen)
    for b in buckets:
        t.messages += b.messages
        t.tool_calls += b.tool_calls
        for name in (*_TOKEN_FIELDS, "cost"):
            t.add_num(name, getattr(b, name))
    return t
