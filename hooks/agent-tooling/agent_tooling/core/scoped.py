"""Shared touched-path and Rule-rendering helpers for agent targets."""

from __future__ import annotations

import os
import re

from .paths import normalize_repo_relative_path

PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+?)\s*$")


def normalize_touched_paths(root, raw_paths):
    """Normalize concrete file paths and ignore directory-only events."""
    result = set()
    for raw_path in raw_paths or ():
        if not isinstance(raw_path, str) or not raw_path:
            continue
        absolute = raw_path if os.path.isabs(raw_path) else os.path.join(root, raw_path)
        if os.path.isdir(absolute):
            continue
        try:
            result.add(normalize_repo_relative_path(root, raw_path))
        except ValueError:
            continue
    return sorted(result)


def extract_patch_paths(tool_input, cwd):
    """Extract file names from apply_patch headers, including new files."""
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    paths = []
    for line in command.splitlines():
        match = PATCH_FILE_RE.match(line.strip())
        if match:
            raw = match.group(1).strip()
            paths.append(raw if os.path.isabs(raw) else os.path.join(cwd, raw))
    return paths


def render_rule_context(found, heading, max_chars):
    """Render selected Rule bodies deterministically within an agent limit."""
    parts = []
    total = 0
    for rule in found:
        block = f"{rule.rule_path} (matched {rule.file_path}):\n{rule.content}\n"
        if total + len(block) > max_chars:
            parts.append(f"(truncated: remaining Rules omitted, over {max_chars} chars)")
            break
        parts.append(block)
        total += len(block)
    return heading + "\n\n" + "\n".join(parts)
