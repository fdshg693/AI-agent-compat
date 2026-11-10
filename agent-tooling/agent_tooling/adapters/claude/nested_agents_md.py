#!/usr/bin/env python3
"""PreToolUse hook: inject nested AGENTS.md that Claude Code does not load
natively. Claude loads nested CLAUDE.md when a file under that directory is
read; AGENTS.md itself is only pulled in via @ imports. This adapter skips
the cwd->root chain (session-start load) and any directory that already has
CLAUDE.md. Candidate is AGENTS.md only (no AGENTS.override.md).

additionalContext is attached next to the tool result and reaches the model
on the next request — not before the tool runs. Never returns
permissionDecision. Fail-open: errors exit 0 with no output.

Copy the built file from agent_tooling/hooks/generated/claude/nested_agents_md.py into .claude/hooks/ and run
register it as scenarios/nested_agents_md/hook.yaml says. This source is not meant to be executed with relative
imports unresolved. Cache dir is nested-agents-md-claude.
"""

import json
import os
import sys

from agent_tooling.core.bash import extract_bash_dirs
from agent_tooling.core.discovery import ancestor_chain, find_repo_root
from agent_tooling.hooks.scenarios.nested_agents_md.discovery import (
    collect_nested_agents_md,
    extract_generic_path_dirs,
)

MAX_CONTEXT_CHARS = 10_000
CACHE_NAME = "nested-agents-md-claude"
NESTED_CANDIDATE_NAMES = ("AGENTS.md",)


def extract_touched_dirs(tool_name, tool_input, cwd):
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool_name == "Bash":
        return extract_bash_dirs(tool_input.get("command", "") or "", cwd)
    return extract_generic_path_dirs(tool_input, cwd, keys=("file_path", "path"))


def skip_dirs_for(root, cwd, touched_dirs):
    skip = set(ancestor_chain(root, cwd))
    for touched in touched_dirs:
        for d in ancestor_chain(root, touched):
            if os.path.isfile(os.path.join(d, "CLAUDE.md")):
                skip.add(d)
    return skip


def render_additional_context(found):
    parts = []
    total = 0
    for rel, content in found:
        block = f"{rel}:\n{content}\n"
        if total + len(block) > MAX_CONTEXT_CHARS:
            parts.append(
                f"(truncated: remaining AGENTS.md files omitted, over {MAX_CONTEXT_CHARS} chars)"
            )
            break
        parts.append(block)
        total += len(block)
    return (
        "The following AGENTS.md files apply to files you are about to read "
        "or edit but were outside the cwd -> project-root path Claude Code "
        "loads at session start, and the directory has no CLAUDE.md of its "
        "own:\n\n" + "\n".join(parts)
    )


def _run():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0

    cwd = event.get("cwd") or os.getcwd()
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    session_id = event.get("session_id", "unknown")

    touched_dirs = extract_touched_dirs(tool_name, tool_input, cwd)
    if not touched_dirs:
        return 0

    root = find_repo_root(cwd)
    found = collect_nested_agents_md(
        root,
        touched_dirs,
        skip_dirs_for(root, cwd, touched_dirs),
        session_id,
        CACHE_NAME,
        candidate_names=NESTED_CANDIDATE_NAMES,
    )
    if not found:
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": render_additional_context(found),
                }
            }
        )
    )
    return 0


def main():
    try:
        return _run()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
