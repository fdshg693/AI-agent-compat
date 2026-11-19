#!/usr/bin/env python3
"""Kilo plugin helper: stdin JSON in, registry update out (no stdout contract).

Spawned by the sibling TypeScript plugin (``event`` hook) once per
``session.created`` / ``session.deleted`` / ``session.updated`` event. The
JSON input carries ``action`` (start/end/cwd), ``session_id`` and ``cwd``.
The PID is the shared Kilo host PID from the TS side (``pid_source: "host"``);
it is the same for every session, so per-session identity is the file name
(agent + session_id). ``session.idle`` is never treated as an end.

This helper prints nothing and never throws; the TS plugin ignores output and
only needs the process to exit 0. Copy both
agent_tooling/hooks/generated/kilo/agent_sessions.py and its .ts sidecar into
.kilo/plugin/. Registry dir is ``AGENT_SESSIONS_DIR``.
"""

import json
import sys

from agent_tooling.hooks.scenarios.agent_sessions.registry import apply_event

AGENT = "kilo"


def _run():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(event, dict):
        return 0

    action = event.get("action")
    session_id = event.get("session_id")
    if not session_id or not action:
        return 0

    apply_event(
        AGENT,
        action,
        session_id,
        cwd=event.get("cwd"),
        pid=event.get("pid") or 0,
        pid_source=event.get("pid_source") or "host",
        hook_event=event.get("event") or action,
    )
    return 0


def main():
    try:
        return _run()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
