"""Which nested AGENTS.md files apply to touched paths."""

import os

from agent_tooling.core.discovery import ancestor_chain

from .cache import load_cache, save_cache

CANDIDATE_NAMES = ("AGENTS.override.md", "AGENTS.md")
DEFAULT_PATH_KEYS = ("file_path", "path")


def path_to_touched_dir(raw_path, cwd):
    if not isinstance(raw_path, str) or not raw_path:
        return None
    abs_path = raw_path if os.path.isabs(raw_path) else os.path.join(cwd, raw_path)
    abs_path = os.path.normpath(abs_path)
    if os.path.isdir(abs_path):
        return abs_path
    return os.path.dirname(abs_path)


def extract_generic_path_dirs(tool_input, cwd, keys=DEFAULT_PATH_KEYS):
    dirs = set()
    if not isinstance(tool_input, dict):
        return dirs
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            abs_path = value if os.path.isabs(value) else os.path.join(cwd, value)
            dirs.add(os.path.dirname(os.path.normpath(abs_path)))
    return dirs


def extract_path_dirs(tool_input, cwd, keys=DEFAULT_PATH_KEYS):
    dirs = set()
    if not isinstance(tool_input, dict):
        return dirs
    for key in keys:
        touched = path_to_touched_dir(tool_input.get(key), cwd)
        if touched:
            dirs.add(touched)
    return dirs


def collect_nested_agents_md(
    root,
    touched_dirs,
    skip_dirs,
    session_id,
    cache_name,
    candidate_names=None,
):
    """Return (repository-relative path, content) for newly found files."""
    if candidate_names is None:
        candidate_names = CANDIDATE_NAMES
    if not touched_dirs:
        return []
    skip = {os.path.normcase(os.path.normpath(d)) for d in skip_dirs}
    cache_path, seen = load_cache(session_id, cache_name)
    found = []
    newly_seen = set()
    for touched_dir in touched_dirs:
        for directory in ancestor_chain(root, touched_dir):
            normalized = os.path.normcase(os.path.normpath(directory))
            if normalized in skip or normalized in seen or normalized in newly_seen:
                continue
            newly_seen.add(normalized)
            for name in candidate_names:
                candidate = os.path.join(directory, name)
                if not os.path.isfile(candidate):
                    continue
                try:
                    with open(candidate, "r", encoding="utf-8", errors="replace") as stream:
                        content = stream.read().strip()
                except Exception:
                    content = ""
                if content:
                    relative = os.path.relpath(candidate, root).replace(os.sep, "/")
                    found.append((relative, content))
                break
    save_cache(cache_path, seen | newly_seen)
    return found
