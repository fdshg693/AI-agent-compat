#!/usr/bin/env python3
"""Cursor sessionStart / sessionEnd adapter for the agent-sessions registry.

Cursor's payload has no ``cwd``; the first ``workspace_roots`` entry is used.
The session id is ``session_id`` (which equals ``conversation_id``). There is
no CWD-change event, so the CWD recorded at sessionStart is kept. Cursor's
``workspaceOpen`` is not used: it omits ``conversation_id`` and cannot be
correlated with a session. These events do not fire for cloud agents, so the
registry only tracks local IDE sessions. Output is silent (sessionStart may
carry ``env``/``additional_context``, but this scenario injects nothing).
Fail-open: any error exits 0.

This is the Cursor adapter source. Copy the built file from
agent_tooling/hooks/generated/cursor/agent_sessions.py beside .cursor/hooks.json
and register both sessionStart and sessionEnd. Registry dir is
``AGENT_SESSIONS_DIR``.
"""

import json
import sys

from agent_tooling.core.sessions import find_agent_pid
from agent_tooling.hooks.scenarios.agent_sessions.registry import apply_event

AGENT = "cursor"


def _workspace_cwd(event):
    roots = event.get("workspace_roots") or []
    if roots and isinstance(roots[0], str) and roots[0]:
        return roots[0]
    return event.get("cwd")


def _run():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(event, dict):
        return 0

    session_id = event.get("session_id") or event.get("conversation_id")
    if not session_id:
        return 0
    name = event.get("hook_event_name") or ""

    if name == "sessionStart":
        pid, pid_source = find_agent_pid()
        apply_event(
            AGENT,
            "start",
            session_id,
            cwd=_workspace_cwd(event),
            pid=pid,
            pid_source=pid_source,
            hook_event=name,
        )
    elif name == "sessionEnd":
        apply_event(AGENT, "end", session_id, hook_event=name)
    return 0


def main():
    try:
        return _run()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
