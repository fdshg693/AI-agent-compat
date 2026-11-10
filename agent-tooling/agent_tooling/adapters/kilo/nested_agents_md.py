#!/usr/bin/env python3
"""Kilo plugin helper: stdin JSON in, {additionalContext} out.

Spawned by the sibling TypeScript plugin (tool.execute.after). Does not
talk to Kilo's plugin API. Candidates are AGENTS.md then AGENT.md. Root
AGENTS.md is skipped. Never rewrite tool args; an empty or missing
additionalContext means the TS plugin leaves output.output alone.

Cache dir is nested-agents-md-kilo. Copy both
agent_tooling/hooks/generated/kilo/nested_agents_md.py and its .ts sidecar into .kilo/plugin/.
"""

import json
import os
import re
import sys

from agent_tooling.core.bash import extract_bash_dirs
from agent_tooling.hooks.scenarios.nested_agents_md.discovery import (
    collect_nested_agents_md,
    extract_path_dirs,
    path_to_touched_dir,
)
from agent_tooling.core.discovery import find_repo_root

MAX_CONTEXT_BYTES = 16_000
CACHE_NAME = "nested-agents-md-kilo"
NESTED_CANDIDATE_NAMES = ("AGENTS.md", "AGENT.md")
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+?)\s*$")
PATH_KEYS = ("filePath", "file_path", "path")


def extract_apply_patch_dirs(tool_input, cwd):
    dirs = set()
    blobs = []
    if isinstance(tool_input, dict):
        for key in ("command", "patch", "patchText", "diff"):
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                blobs.append(value)
        for value in tool_input.values():
            if isinstance(value, str) and value not in blobs:
                blobs.append(value)
    elif isinstance(tool_input, str):
        blobs.append(tool_input)
    for blob in blobs:
        for line in blob.splitlines():
            m = PATCH_FILE_RE.match(line.strip())
            if not m:
                continue
            touched = path_to_touched_dir(m.group(1).strip(), cwd)
            if touched:
                dirs.add(touched)
    return dirs


def extract_touched_dirs(tool_name, tool_input, cwd):
    if not isinstance(tool_input, dict):
        tool_input = {}
    if tool_name in ("bash", "Bash"):
        return extract_bash_dirs(tool_input.get("command", "") or "", cwd)
    if tool_name == "apply_patch":
        return extract_apply_patch_dirs(tool_input, cwd)
    return extract_path_dirs(tool_input, cwd, keys=PATH_KEYS)


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
        "The following nested AGENTS.md files apply to the tool call that "
        "just ran (outside the project-root file loaded at session start):\n\n" + "\n".join(parts)
    )


def _run():
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0

    cwd = event.get("cwd") or os.getcwd()
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    session_id = event.get("session_id") or "unknown"

    touched_dirs = extract_touched_dirs(tool_name, tool_input, cwd)
    if not touched_dirs:
        print(json.dumps({"additionalContext": ""}))
        return 0

    root = find_repo_root(cwd)
    found = collect_nested_agents_md(
        root,
        touched_dirs,
        {root},
        session_id,
        CACHE_NAME,
        candidate_names=NESTED_CANDIDATE_NAMES,
    )
    additional = render_additional_context(found) if found else ""
    print(json.dumps({"additionalContext": additional}))
    return 0


def main():
    try:
        return _run()
    except Exception:
        try:
            print(json.dumps({"additionalContext": ""}))
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
