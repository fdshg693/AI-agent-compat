"""Treat Windows junctions like symlinks when scanning directories.

``Path.is_symlink()`` / ``os.path.islink()`` are False for a junction, and
``Path.rglob`` / ``os.walk`` descend into one, while ``rglob("**")`` does not
descend into a real directory symlink. ``find_files`` walks without entering
either kind, so a tree reachable through a junction is read once. A same-named
helper lives in the umbrella repository's maintenance/scripts/links/fs.py;
agent-tooling keeps its own copy because it is distributed on its own.
"""

from __future__ import annotations

import fnmatch
import os
import stat
from pathlib import Path

_MOUNT_POINT = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def is_link_like(path) -> bool:
    """True for a symlink or a junction (never follows the link itself)."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return getattr(st, "st_reparse_tag", 0) == _MOUNT_POINT


def find_files(root: Path, pattern: str) -> list[Path]:
    """Files under ``root`` whose name matches ``pattern``, not entering linked dirs."""
    found = []
    for dir_path, dir_names, file_names in os.walk(root):
        dir_names[:] = [
            name for name in dir_names if not is_link_like(os.path.join(dir_path, name))
        ]
        found.extend(Path(dir_path) / name for name in file_names if fnmatch.fnmatch(name, pattern))
    return found
