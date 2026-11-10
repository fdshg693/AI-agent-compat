#!/usr/bin/env python3
"""Antigravity pseudo session lifecycle adapter for the agent-sessions registry.

Antigravity has no SessionStart/SessionEnd event, so this artifact uses pseudo
events: the first ``PreInvocation`` (``invocationNum == 0``) starts a session
and ``Stop`` with ``fullyIdle`` removes it. The CWD comes from the first
``workspacePaths`` entry and is refreshed from ``toolCall.args.Cwd`` on a
``run_command`` PreToolUse call when present. Sessions whose ``Stop`` never
arrives are eventually reported as stale by the CLI's PID/last-seen check.

Output contracts are strict: PreToolUse must return ``{"decision":"allow"}``
(never deny/ask), and Stop must return ``{}`` (returning ``continue`` would
keep the agent running). PreInvocation and unknown payloads return ``{}``.
Fail-open: any error exits 0 without stalling a gate.

Copy the built file from
agent_tooling/hooks/generated/antigravity/agent_sessions.py into
.agents/hooks/ and register PreToolUse (matcher
``run_command``), PreInvocation, and Stop in .agents/hooks.json. Registry dir
is ``AGENT_SESSIONS_DIR``.
"""

import json
import sys

from agent_tooling.core.sessions import find_agent_pid
from agent_tooling.hooks.scenarios.agent_sessions.registry import apply_event

AGENT = "antigravity"


def _workspace_cwd(event):
    paths = event.get("workspacePaths") or []
    if paths and isinstance(paths[0], str) and paths[0]:
        return paths[0]
    return None


def _handle_pre_tool_use(event):
    session_id = event.get("conversationId")
    args = (event.get("toolCall") or {}).get("args") or {}
    cwd = args.get("Cwd") if isinstance(args, dict) else None
    if session_id and isinstance(cwd, str) and cwd:
        apply_event(AGENT, "cwd", session_id, cwd=cwd, hook_event="PreToolUse")
    return {"decision": "allow"}


def _handle_pre_invocation(event):
    session_id = event.get("conversationId")
    if session_id and event.get("invocationNum") == 0:
        pid, pid_source = find_agent_pid()
        apply_event(
            AGENT,
            "start",
            session_id,
            cwd=_workspace_cwd(event),
            pid=pid,
            pid_source=pid_source,
            hook_event="PreInvocation",
        )
    return {}


def _handle_stop(event):
    session_id = event.get("conversationId")
    if session_id and event.get("fullyIdle") is True:
        apply_event(AGENT, "end", session_id, hook_event="Stop")
    return {}


def _dispatch(event):
    if isinstance(event.get("toolCall"), dict):
        return _handle_pre_tool_use(event)
    if "invocationNum" in event:
        return _handle_pre_invocation(event)
    if "fullyIdle" in event or "terminationReason" in event or "executionNum" in event:
        return _handle_stop(event)
    # Unknown payload: fail-open without stalling a PreToolUse gate.
    return {"decision": "allow"}


def _run():
    try:
        event = json.load(sys.stdin)
        output = _dispatch(event)
    except Exception:
        output = {"decision": "allow"}
    try:
        print(json.dumps(output))
    except Exception:
        pass
    return 0


def main():
    try:
        return _run()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
