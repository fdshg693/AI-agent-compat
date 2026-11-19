"""Path helpers: per-tool roots, project normalization, link-safe scanning.

Roots resolve through environment variables so tests and other machines can point
the CLI at any directory:

- ``AGENT_LOGS_HOME`` replaces the user home (``~``) for every adapter.
- ``AGENT_LOGS_APPDATA`` replaces the per-user application data directory
  (``%APPDATA%`` on Windows, ``~/Library/Application Support`` on macOS,
  ``$XDG_CONFIG_HOME`` or ``~/.config`` elsewhere).
- ``AGENT_LOGS_<TOOL>_DIR`` replaces one adapter's main root (documented per adapter).
"""

from __future__ import annotations

import os
import re
import stat
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

_MOUNT_POINT = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def home() -> Path:
    env = os.environ.get("AGENT_LOGS_HOME")
    return Path(env) if env else Path.home()


def appdata() -> Path:
    env = os.environ.get("AGENT_LOGS_APPDATA")
    if env:
        return Path(env)
    if os.environ.get("AGENT_LOGS_HOME"):
        # hermetic: never escape the overridden home
        return home() / "AppData" / "Roaming"
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def tool_root(tool: str, default: Path) -> Path:
    """``AGENT_LOGS_<TOOL>_DIR`` if set, else ``default``."""
    env = os.environ.get(f"AGENT_LOGS_{tool.upper()}_DIR")
    return Path(env) if env else default


_DRIVE = re.compile(r"^/?([A-Za-z]):(?=/|$)")


def normalize_path(value: str | os.PathLike | None) -> str | None:
    """Comparable project path: ``file://`` decoded, ``/`` separators, upper drive letter,
    no trailing slash. ``None`` / empty stays ``None``."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.lower().startswith("file:"):
        parsed = urlparse(s)
        s = unquote(parsed.path)
        if parsed.netloc and parsed.netloc not in ("", "localhost"):
            s = f"//{parsed.netloc}{s}"
    s = s.replace("\\", "/")
    m = _DRIVE.match(s)
    if m:
        s = m.group(1).upper() + ":" + s[m.end() :]
        if s == f"{m.group(1).upper()}:":
            s += "/"
    if len(s) > 1 and s.endswith("/") and not re.fullmatch(r"[A-Z]:/", s):
        s = s.rstrip("/")
    return s


def project_matches(project: str | None, needle: str | None) -> bool:
    if not needle:
        return True
    if not project:
        return False
    n = normalize_path(needle) or needle
    return n.lower() in project.lower()


def is_link_like(path: str | os.PathLike) -> bool:
    """True for a symlink or a Windows junction (never follows the link itself).

    Same contract as agent-tooling's ``core/fs_links.is_link_like``; kept as a copy
    because the packages are distributed independently.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return getattr(st, "st_reparse_tag", 0) == _MOUNT_POINT


def walk_files(root: Path, *, suffixes: tuple[str, ...] | None = None) -> Iterator[Path]:
    """Files under ``root`` (recursive) without entering symlinked/junction dirs."""
    if not root.is_dir():
        return
    for dir_path, dir_names, file_names in os.walk(root):
        dir_names[:] = [d for d in dir_names if not is_link_like(os.path.join(dir_path, d))]
        for name in file_names:
            if suffixes is None or name.endswith(suffixes):
                p = Path(dir_path) / name
                if not is_link_like(p):
                    yield p


def list_dir(root: Path) -> list[Path]:
    """Direct children of ``root`` that are not links (empty when missing)."""
    try:
        return [p for p in root.iterdir() if not is_link_like(p)]
    except OSError:
        return []


def mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return None
