#!/usr/bin/env python3
"""PreToolUse hook: inject AGENTS.md files that Codex's own session-start
discovery does NOT cover.

Codex builds its instruction chain once per session by walking from the
project root down to the *initial* cwd only (see
codex-plugins/meta/skills/codex-memory/SKILL.md section 2). Files read or
edited outside that root->cwd path never get their local AGENTS.md
pulled in automatically -- unlike Claude Code's CLAUDE.md, which loads a
subdirectory's CLAUDE.md the moment Claude reads any file under it (see
skills/plugins/cc-knowledge/skills/claude-code-memory/memory.md line 31), Codex
has no dedicated "Read" tool: apply_patch is the only structured
file-editing tool, and file reads normally go through arbitrary shell
commands (Bash / exec_command). This hook fires on apply_patch and Bash
calls, tries to work out which files/directories are actually being
touched (structured parsing for apply_patch, a best-effort heuristic
over common read commands for Bash), finds the AGENTS.override.md /
AGENTS.md files for their ancestor directories, skips whatever the
root->cwd walk already covered, and feeds the rest back in as
additionalContext.

The Bash-side detection is inherently a heuristic (arbitrary shell
commands can read files in ways this script won't recognize) and is not
a substitute for the deterministic apply_patch coverage.

Never blocks: on any error, it exits 0 with no output so the tool call
is unaffected.

This is the Codex adapter source. Copy the built file from
agent_tooling/hooks/generated/codex/nested_agents_md.py rather than running this module as a script
(relative imports). Cache dir is nested-agents-md-codex so it does not
collide with the live .codex/hooks/ script (codex-nested-agents-md).
"""

import json
import os
import re
import sys

from agent_tooling.core.bash import extract_bash_dirs
from agent_tooling.core.discovery import ancestor_chain, find_repo_root
from agent_tooling.hooks.scenarios.nested_agents_md.discovery import (
    collect_nested_agents_md,
    extract_generic_path_dirs,
)

MAX_CONTEXT_BYTES = 16_000
CACHE_NAME = "nested-agents-md-codex"
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+?)\s*$")


def extract_apply_patch_dirs(tool_input, cwd):
    dirs = set()
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    for line in command.splitlines():
        m = PATCH_FILE_RE.match(line.strip())
        if not m:
            continue
        raw_path = m.group(1).strip()
        abs_path = raw_path if os.path.isabs(raw_path) else os.path.join(cwd, raw_path)
        dirs.add(os.path.dirname(os.path.normpath(abs_path)))
    return dirs


def extract_touched_dirs(tool_name, tool_input, cwd):
    if tool_name == "apply_patch":
        return extract_apply_patch_dirs(tool_input, cwd)
    if tool_name == "Bash":
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        return extract_bash_dirs(command, cwd)
    return extract_generic_path_dirs(tool_input, cwd)


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
    return (
        "The following AGENTS.md files apply to files you are about to read "
        "or edit but were outside the project-root -> initial-cwd path Codex "
        "loads automatically at session start:\n\n" + "\n".join(parts)
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
    skip_dirs = ancestor_chain(root, cwd)
    found = collect_nested_agents_md(
        root,
        touched_dirs,
        skip_dirs,
        session_id,
        CACHE_NAME,
    )
    if not found:
        return 0

    additional_context = render_additional_context(found)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": additional_context,
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
