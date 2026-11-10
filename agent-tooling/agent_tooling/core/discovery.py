"""Pure repository and ancestor path discovery helpers."""

from __future__ import annotations

import os


def find_repo_root(start_dir: str) -> str:
    current = os.path.abspath(start_dir)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(start_dir)
        current = parent


def ancestor_chain(root: str, target_dir: str) -> list[str]:
    """Return directories from root down to target_dir, inclusive."""
    root = os.path.normcase(os.path.normpath(root))
    target_dir = os.path.normpath(target_dir)
    target_norm = os.path.normcase(target_dir)
    if target_norm != root and not target_norm.startswith(root + os.sep):
        return []
    chain = []
    current = target_dir
    while True:
        chain.append(current)
        if os.path.normcase(os.path.normpath(current)) == root:
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    chain.reverse()
    return chain
