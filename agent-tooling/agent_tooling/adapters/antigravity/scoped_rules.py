#!/usr/bin/env python3
"""Antigravity PreToolUse/PreInvocation target for scoped Rules."""

from __future__ import annotations

import json
import os
import sys

from agent_tooling.core.bash import extract_bash_paths
from agent_tooling.core.discovery import find_repo_root
from agent_tooling.core.scoped import normalize_touched_paths, render_rule_context
from agent_tooling.hooks.common.cache import load_cache, save_cache
from agent_tooling.hooks.scenarios.scoped_rules.discovery import discover_scoped_rules

MAX_CONTEXT_BYTES = 16_000
PENDING_CACHE_NAME = "scoped-rules-antigravity-pending"


def _cwd(event):
    args = (event.get("toolCall") or {}).get("args") or {}
    value = args.get("Cwd")
    if isinstance(value, str) and value:
        return value
    workspaces = event.get("workspacePaths") or []
    return workspaces[0] if workspaces and isinstance(workspaces[0], str) else os.getcwd()


def _root(event, cwd):
    workspaces = event.get("workspacePaths") or []
    return (
        os.path.normpath(workspaces[0])
        if workspaces and isinstance(workspaces[0], str)
        else find_repo_root(cwd)
    )


def _pending_path(session_id):
    return load_cache(session_id, PENDING_CACHE_NAME)


def _add_pending(session_id, paths):
    cache_path, current = _pending_path(session_id)
    save_cache(cache_path, current | set(paths))


def _take_pending(session_id):
    cache_path, current = _pending_path(session_id)
    save_cache(cache_path, set())
    return current


def _pre_tool(event):
    args = (event.get("toolCall") or {}).get("args") or {}
    cwd = _cwd(event)
    values = [args.get(key) for key in ("AbsolutePath", "TargetFile")]
    command = args.get("CommandLine")
    if isinstance(command, str) and command:
        values.extend(extract_bash_paths(command, cwd))
    paths = normalize_touched_paths(_root(event, cwd), values)
    if paths:
        _add_pending(event.get("conversationId") or "unknown", paths)
    print(json.dumps({"decision": "allow"}))


def _pre_invocation(event):
    session_id = event.get("conversationId") or "unknown"
    pending = _take_pending(session_id)
    if not pending:
        print(json.dumps({}))
        return
    root = _root(event, _cwd(event))
    found = discover_scoped_rules(root, pending, session_id=session_id)
    if not found:
        print(json.dumps({}))
        return
    print(
        json.dumps(
            {
                "injectSteps": [
                    {
                        "ephemeralMessage": render_rule_context(
                            found,
                            "The following Claude Rules apply to paths touched since the last model invocation:",
                            MAX_CONTEXT_BYTES,
                        )
                    }
                ]
            }
        )
    )


def _run():
    try:
        event = json.load(sys.stdin)
        if isinstance(event.get("toolCall"), dict):
            _pre_tool(event)
        elif "invocationNum" in event:
            _pre_invocation(event)
        else:
            print(json.dumps({"decision": "allow"}))
    except Exception:
        print(json.dumps({"decision": "allow"}))
    return 0


if __name__ == "__main__":
    sys.exit(_run())
