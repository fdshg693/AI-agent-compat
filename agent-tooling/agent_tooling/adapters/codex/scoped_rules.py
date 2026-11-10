#!/usr/bin/env python3
"""Codex PreToolUse target for the scoped-rules scenario."""

from __future__ import annotations

import json
import os
import sys

from agent_tooling.core.bash import extract_bash_paths
from agent_tooling.core.discovery import find_repo_root
from agent_tooling.core.scoped import (
    extract_patch_paths,
    normalize_touched_paths,
    render_rule_context,
)
from agent_tooling.hooks.scenarios.scoped_rules.discovery import discover_scoped_rules

MAX_CONTEXT_BYTES = 16_000


def _raw_paths(tool_name, tool_input, cwd):
    if tool_name == "apply_patch":
        return extract_patch_paths(tool_input, cwd)
    if tool_name == "Bash":
        return extract_bash_paths((tool_input or {}).get("command", "") or "", cwd)
    return []


def _run():
    try:
        event = json.load(sys.stdin)
        cwd = event.get("cwd") or os.getcwd()
        root = find_repo_root(cwd)
        paths = normalize_touched_paths(
            root, _raw_paths(event.get("tool_name", ""), event.get("tool_input", {}), cwd)
        )
        found = discover_scoped_rules(root, paths, session_id=event.get("session_id", "unknown"))
        if not found:
            return 0
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": render_rule_context(
                            found,
                            "The following Claude Rules apply to paths you are about to read or edit:",
                            MAX_CONTEXT_BYTES,
                        ),
                    }
                }
            )
        )
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(_run())
