"""Cross-adapter iteration, filtering and search."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from agent_logs.adapters.base import Adapter
from agent_logs.model import Event, Filters, Session
from agent_logs.paths import project_matches


def session_in_range(s: Session, f: Filters) -> bool:
    start = s.started_at or s.ended_at
    end = s.ended_at or s.started_at
    if f.since and (end is None or end < f.since):
        return False
    if f.until and (start is None or start > f.until):
        return False
    return True


def filter_sessions(sessions: Iterator[Session], f: Filters) -> Iterator[Session]:
    for s in sessions:
        if f.tools and s.tool not in f.tools:
            continue
        if not session_in_range(s, f):
            continue
        if not project_matches(s.project or s.cwd, f.project):
            continue
        yield s


def iter_sessions(adapters: list[Adapter], f: Filters) -> Iterator[Session]:
    """Sessions of every adapter; an adapter crash becomes a warning."""
    for a in adapters:
        try:
            yield from filter_sessions(a.iter_sessions(f), f)
        except Exception as exc:  # noqa: BLE001
            a.warn(f"listing failed ({type(exc).__name__}: {exc})")


def iter_events(adapter: Adapter, s: Session, f: Filters | None = None) -> Iterator[Event]:
    try:
        for e in adapter.iter_events(s):
            if f is not None:
                if f.role and e.role != f.role:
                    continue
                if f.since and e.ts and e.ts < f.since:
                    continue
                if f.until and e.ts and e.ts > f.until:
                    continue
            yield e
    except Exception as exc:  # noqa: BLE001
        adapter.warn(f"{s.id}: reading events failed ({type(exc).__name__}: {exc})")


def find_session(adapters: list[Adapter], ref: str) -> tuple[Adapter, Session] | None:
    """Resolve ``<id>``, an id prefix, or ``<tool>:<id>``. Exact match wins over prefix."""
    tool = None
    if ":" in ref:
        head, tail = ref.split(":", 1)
        if head in {a.name for a in adapters}:
            tool, ref = head, tail
    prefix_hits: list[tuple[Adapter, Session]] = []
    for a in adapters:
        if tool and a.name != tool:
            continue
        try:
            for s in a.iter_sessions(Filters()):
                if s.id == ref:
                    return a, s
                if s.id.startswith(ref):
                    prefix_hits.append((a, s))
        except Exception as exc:  # noqa: BLE001
            a.warn(f"listing failed ({type(exc).__name__}: {exc})")
    if len(prefix_hits) == 1:
        return prefix_hits[0]
    if len(prefix_hits) > 1:
        ids = ", ".join(f"{a.name}:{s.id}" for a, s in prefix_hits[:5])
        raise LookupError(f"ambiguous session prefix {ref!r}: {ids}")
    return None


@dataclass
class Hit:
    session: Session
    event: Event
    snippet: str


class Matcher:
    def __init__(self, pattern: str, *, regex: bool, case_sensitive: bool) -> None:
        flags = 0 if case_sensitive else re.IGNORECASE
        self.rx = re.compile(pattern if regex else re.escape(pattern), flags)

    def find(self, text: str | None) -> re.Match | None:
        return self.rx.search(text) if text else None


def snippet(text: str, m: re.Match, width: int) -> str:
    """``width`` characters of context around the match, one line."""
    half = max(width // 2, 10)
    start = max(m.start() - half, 0)
    end = min(m.end() + half, len(text))
    body = text[start:end].replace("\r", " ").replace("\n", " ⏎ ")
    return ("…" if start > 0 else "") + body + ("…" if end < len(text) else "")


def search(
    adapters: list[Adapter],
    f: Filters,
    matcher: Matcher,
    *,
    kinds: set[str] | None = None,
    width: int = 120,
) -> Iterator[Hit]:
    by_name = {a.name: a for a in adapters}
    for s in iter_sessions(adapters, f):
        for e in iter_events(by_name[s.tool], s, f):
            if kinds and e.kind not in kinds:
                continue
            for field_text in (e.text, e.tool_name):
                m = matcher.find(field_text)
                if m:
                    yield Hit(s, e, snippet(field_text, m, width))
                    break
