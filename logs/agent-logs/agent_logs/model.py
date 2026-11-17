"""Normalized schema shared by every adapter.

Values an adapter cannot obtain stay ``None`` (never ``0``) so "not recorded" and
"recorded as zero" remain distinguishable. All datetimes are timezone-aware UTC.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any

# Event.kind values
KINDS = (
    "message",
    "reasoning",
    "tool_call",
    "tool_result",
    "system",
    "summary",
    "usage",
    "turn_end",
    "raw",
)
# Event.role values (None when a record has no meaningful role)
ROLES = ("user", "assistant", "system", "tool")


@dataclass
class Session:
    id: str
    tool: str  # adapter name: claude / cursor / cline / kilo / antigravity / codex
    source: str | None = None  # sub-system within the tool (cli, ide, vscode-legacy, subagent, ...)
    project: str | None = None  # normalized project path (see paths.normalize_path)
    cwd: str | None = None  # raw cwd as recorded
    started_at: datetime | None = None
    ended_at: datetime | None = None
    model: str | None = None  # main / last model
    title: str | None = None
    parent_id: str | None = None
    message_count: int | None = None  # user + assistant message events
    tool_call_count: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_cache_read: int | None = None
    tokens_cache_write: int | None = None
    cost: float | None = None  # USD
    path: str | None = None  # main file / DB the session was read from
    # Adapter-private locator (never serialized): whatever iter_events needs.
    ref: Any = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        out = {}
        for f in fields(self):
            if f.name == "ref":
                continue
            out[f.name] = _jsonable(getattr(self, f.name))
        return out


@dataclass
class Event:
    session_id: str
    tool: str
    ts: datetime | None = None
    role: str | None = None
    kind: str = "message"
    tool_name: str | None = None  # for tool_call / tool_result
    call_id: str | None = None
    text: str | None = None  # searchable text (tool_call: serialized input)
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_cache_read: int | None = None
    tokens_cache_write: int | None = None
    cost: float | None = None
    raw: Any = field(default=None, repr=False)  # original record; only emitted with --raw

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        d = {k: _jsonable(v) for k, v in asdict(self).items() if k != "raw"}
        if include_raw:
            d["raw"] = self.raw
        return d


@dataclass
class SourceInfo:
    """One storage location an adapter knows about (``agent-logs sources``)."""

    tool: str
    source: str
    path: str
    exists: bool
    count: int | None = None  # sessions / files found (None when not counted)
    last_modified: datetime | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: _jsonable(v) for k, v in asdict(self).items()}


@dataclass
class Filters:
    tools: list[str] | None = None
    since: datetime | None = None
    until: datetime | None = None
    project: str | None = None  # case-insensitive substring of the normalized project path
    role: str | None = None


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value
