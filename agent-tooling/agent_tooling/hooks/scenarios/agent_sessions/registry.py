"""Apply normalized agent-session events to the per-user registry.

Adapters parse their tool payload, normalize it to
``(agent, action, session_id, cwd, pid, pid_source, hook_event)`` and call
``apply_event``.  This layer is deliberately thin and fail-open: any error is
swallowed so the hook can exit 0 without stopping the agent.
"""

from __future__ import annotations

from agent_tooling.core.sessions import (
    end_session,
    start_session,
    update_session,
)

from .definition import ACTIONS, SCENARIO_ID

__all__ = ["SCENARIO_ID", "apply_event"]


def apply_event(
    agent,
    action,
    session_id,
    *,
    cwd=None,
    pid=0,
    pid_source="unknown",
    hook_event=None,
    directory=None,
    now=None,
):
    """Apply one event. Returns a truthy result on success, else ``False``."""
    try:
        if not isinstance(agent, str) or not agent.strip():
            return False
        if action not in ACTIONS:
            return False
        if action == "start":
            return bool(
                start_session(
                    agent,
                    session_id,
                    cwd=cwd,
                    pid=pid,
                    pid_source=pid_source,
                    hook_event=hook_event,
                    directory=directory,
                    now=now,
                )
            )
        if action == "end":
            return end_session(agent, session_id, directory=directory)
        if action == "cwd":
            if cwd is None:
                return False
            return bool(
                update_session(
                    agent,
                    session_id,
                    cwd=cwd,
                    hook_event=hook_event,
                    directory=directory,
                    now=now,
                )
            )
        return bool(
            update_session(
                agent,
                session_id,
                hook_event=hook_event,
                directory=directory,
                now=now,
            )
        )
    except Exception:
        return False
