"""Adapter contract.

Each adapter reads one tool's local logs read-only and yields normalized objects:

- ``detect()``: every storage location it knows (exists or not) as ``SourceInfo``.
- ``iter_sessions(filters)``: ``Session`` objects. Adapters MAY use ``filters`` to skip
  work early (e.g. file mtime < ``filters.since``) but need not apply them exactly;
  ``query.filter_sessions`` applies all filters afterwards. Session token/cost totals
  must already be de-duplicated (prefer the tool's own cumulative values).
- ``iter_events(session)``: ``Event`` objects in chronological order for a session
  returned by ``iter_sessions``. Tokens on events are counted once per model response.

Rules: never open credential files, never write, never follow links, keep going on
per-file errors (``self.warn``) instead of raising.
"""

from __future__ import annotations

from collections.abc import Iterator

from agent_logs.model import Event, Filters, Session, SourceInfo


class Adapter:
    name: str = ""
    env_var: str = ""  # AGENT_LOGS_<TOOL>_DIR

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warn(self, message: str) -> None:
        self.warnings.append(f"{self.name}: {message}")

    def detect(self) -> list[SourceInfo]:
        raise NotImplementedError

    def iter_sessions(self, filters: Filters) -> Iterator[Session]:
        raise NotImplementedError

    def iter_events(self, session: Session) -> Iterator[Event]:
        raise NotImplementedError
