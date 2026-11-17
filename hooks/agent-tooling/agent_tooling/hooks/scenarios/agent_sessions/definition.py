"""Contract for the agent-sessions hook scenario.

This scenario only writes/removes entries in the per-user session registry
(``agent_tooling.core.sessions``) and injects no context.  One artifact per
agent branches on the normalized ``action`` derived from the tool event:

- ``start``: create the entry (only ``start`` creates files).
- ``end``: delete the entry.
- ``cwd``: update CWD and ``last_seen`` when the entry exists.
- ``heartbeat``: refresh ``last_seen`` only.

``pid_source`` records how the PID was obtained (``agent`` ancestor, ``host``
shared server, or ``unknown``) and drives the liveness fallback in the store.
"""

from __future__ import annotations

# Re-exported from the registry store rather than redefined, so the inlined
# hook has a single definition of each.
from agent_tooling.core.sessions import PID_SOURCES as PID_SOURCES
from agent_tooling.core.sessions import SCHEMA_VERSION as SCHEMA_VERSION

SCENARIO_ID: str = "agent_sessions"
ACTIONS: tuple[str, ...] = ("start", "end", "cwd", "heartbeat")
ENTRY_FIELDS: tuple[str, ...] = (
    "schema",
    "agent",
    "session_id",
    "pid",
    "pid_source",
    "cwd",
    "started_at",
    "last_seen",
    "hook_event",
)


def is_action(value) -> bool:
    return isinstance(value, str) and value in ACTIONS
