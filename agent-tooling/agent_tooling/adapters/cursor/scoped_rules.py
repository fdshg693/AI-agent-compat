#!/usr/bin/env python3
"""Cursor postToolUse target for the scoped-rules scenario."""

from __future__ import annotations

import json
import os
import sys

from agent_tooling.core.bash import extract_bash_paths
from agent_tooling.core.discovery import find_repo_root
from agent_tooling.core.scoped import normalize_touched_paths, render_rule_context
from agent_tooling.hooks.scenarios.scoped_rules.discovery import discover_scoped_rules

MAX_CONTEXT_BYTES = 16_000


def _raw_paths(tool_name, tool_input, cwd):
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool_name == "Shell":
        shell_cwd = tool_input.get("working_directory") or tool_input.get("cwd") or cwd
        return extract_bash_paths(tool_input.get("command", "") or "", shell_cwd)
    values = []
    for key in ("path", "file_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            values.append(value if os.path.isabs(value) else os.path.join(cwd, value))
    return values


def _run():
    try:
        event = json.load(sys.stdin)
        cwd = event.get("cwd") or (event.get("workspace_roots") or [os.getcwd()])[0]
        root = find_repo_root(cwd)
        paths = normalize_touched_paths(
            root, _raw_paths(event.get("tool_name", ""), event.get("tool_input", {}), cwd)
        )
        found = discover_scoped_rules(
            root,
            paths,
            session_id=event.get("conversation_id") or event.get("session_id") or "unknown",
        )
        if not found:
            return 0
        print(
            json.dumps(
                {
                    "additional_context": render_rule_context(
                        found,
                        "The following Claude Rules apply to the paths just touched:",
                        MAX_CONTEXT_BYTES,
                    )
                }
            )
        )
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(_run())
