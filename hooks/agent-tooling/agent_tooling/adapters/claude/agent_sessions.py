#!/usr/bin/env python3
"""Claude Code adapter for the agent-sessions registry scenario. One artifact is
registered for SessionStart (create), CwdChanged (update ``new_cwd``), and
SessionEnd (delete); the branch is chosen from ``hook_event_name``.

SessionStart stdout is injected into Claude's context, so this hook prints
nothing. SessionEnd has a 1.5 second default timeout, so ``end`` only removes
the file. The recorded PID is the first non-shell ancestor from
``find_agent_pid`` (``pid_source: "agent"``). Fail-open: any error exits 0.

Copy the built file from
agent_tooling/hooks/generated/claude/agent_sessions.py into .claude/hooks/
and register it as scenarios/agent_sessions/hook.yaml says. Registry dir is ``AGENT_SESSIONS_DIR``.
"""

import json
import sys

from agent_tooling.core.sessions import find_agent_pid
from agent_tooling.hooks.scenarios.agent_sessions.registry import apply_event

AGENT = "claude"


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
    cwd = event.get("cwd")

    if name == "SessionStart":
        pid, pid_source = find_agent_pid()
        apply_event(
            AGENT,
            "start",
            session_id,
            cwd=cwd,
            pid=pid,
            pid_source=pid_source,
            hook_event=name,
        )
    elif name == "CwdChanged":
        apply_event(
            AGENT,
            "cwd",
            session_id,
            cwd=event.get("new_cwd") or cwd,
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
