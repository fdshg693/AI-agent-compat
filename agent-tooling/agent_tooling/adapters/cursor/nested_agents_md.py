#!/usr/bin/env python3
"""postToolUse hook: inject nested AGENTS.md after Read/Write/Grep/Delete/Shell.

Cursor already concatenates nested AGENTS.md for the tree being worked in.
This complete is a reference implementation and still extracts paths from
Read/Write (matcher is not Shell-only). Root AGENTS.md is skipped; the
session cache suppresses re-injection of the same directory.

preToolUse has no additional-context field. Output is additional_context
only — never permission or updated_input. Fail-open.

Copy the built file from agent_tooling/hooks/generated/cursor/nested_agents_md.py. Command in hooks.json is
repository-root relative. Cache dir is nested-agents-md-cursor.
"""

import json
import os
import sys

from agent_tooling.core.bash import extract_bash_dirs
from agent_tooling.core.discovery import find_repo_root
from agent_tooling.hooks.scenarios.nested_agents_md.discovery import (
    collect_nested_agents_md,
    extract_path_dirs,
)

MAX_CONTEXT_BYTES = 16_000
CACHE_NAME = "nested-agents-md-cursor"
NESTED_CANDIDATE_NAMES = ("AGENTS.md",)


def extract_touched_dirs(tool_name, tool_input, cwd):
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool_name == "Shell":
        command = tool_input.get("command", "") or ""
        shell_cwd = tool_input.get("working_directory") or tool_input.get("cwd") or cwd
        return extract_bash_dirs(command, shell_cwd)
    return extract_path_dirs(tool_input, cwd, keys=("path", "file_path"))


def skip_dirs_for(root, event):
    skip = {os.path.normpath(root)}
    for workspace in event.get("workspace_roots") or []:
        if isinstance(workspace, str) and workspace:
            skip.add(os.path.normpath(workspace))
    return skip


def render_additional_context(found):
    parts = []
    total = 0
    for rel, content in found:
        block = f"{rel}:\n{content}\n"
        if total + len(block) > MAX_CONTEXT_BYTES:
            parts.append(
                f"(truncated: remaining AGENTS.md files omitted, over {MAX_CONTEXT_BYTES} bytes)"
            )
            break
        parts.append(block)
        total += len(block)
    return "The following nested AGENTS.md files apply to the paths just touched:\n\n" + "\n".join(
        parts
    )


def _run():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0

    cwd = event.get("cwd") or os.getcwd()
    if not event.get("cwd"):
        roots = event.get("workspace_roots") or []
        if roots and isinstance(roots[0], str) and roots[0]:
            cwd = roots[0]

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    session_id = event.get("conversation_id") or event.get("session_id") or "unknown"

    touched_dirs = extract_touched_dirs(tool_name, tool_input, cwd)
    if not touched_dirs:
        return 0

    root = find_repo_root(cwd)
    found = collect_nested_agents_md(
        root,
        touched_dirs,
        skip_dirs_for(root, event),
        session_id,
        CACHE_NAME,
        candidate_names=NESTED_CANDIDATE_NAMES,
    )
    if not found:
        return 0

    print(json.dumps({"additional_context": render_additional_context(found)}))
    return 0


def main():
    try:
        return _run()
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
