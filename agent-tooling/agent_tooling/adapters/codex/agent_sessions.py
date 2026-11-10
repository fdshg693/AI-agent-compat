#!/usr/bin/env python3
"""Codex SessionStart / SessionEnd adapter for the agent-sessions registry.

Codex has no CWD-change event, so the session keeps the CWD recorded at
SessionStart. Both events are silent: SessionStart stdout is treated as
developer context and must stay empty, and SessionEnd must finish quickly
(default 1 second, 3 seconds maximum) so it only removes the file. The
recorded PID is the first non-shell ancestor (``pid_source: "agent"``).
Fail-open: any error exits 0.

This is the Codex adapter source. Copy the built file from
agent_tooling/hooks/generated/codex/agent_sessions.py into .codex/hooks.json
(register both SessionStart and SessionEnd). Registry dir is
``AGENT_SESSIONS_DIR``.
"""

import json
import sys

from agent_tooling.core.sessions import find_agent_pid
from agent_tooling.hooks.scenarios.agent_sessions.registry import apply_event

AGENT = "codex"


def _run():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(event, dict):
        return 0

    session_id = event.get("session_id")
    if not session_id:
        return 0
    name = event.get("hook_event_name") or ""

    if name == "SessionStart":
        pid, pid_source = find_agent_pid()
        apply_event(
            AGENT,
            "start",
            session_id,
            cwd=event.get("cwd"),
            pid=pid,
            pid_source=pid_source,
            hook_event=name,
        )
    elif name == "SessionEnd":
        apply_event(AGENT, "end", session_id, hook_event=name)
    return 0


def main():
    try:
        return _run()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
