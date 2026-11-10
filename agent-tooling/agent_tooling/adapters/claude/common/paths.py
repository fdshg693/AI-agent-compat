"""Install-location-independent path resolution for the Claude-only hooks.

Two kinds of paths:

- ``hook_dir()``: the directory the running hook file is installed in. After
  the build inlines this module, ``__file__`` is the installed hook itself, so
  the hook's own files -- ``config/<hook id>.yaml``, ``.env``, ``state/``,
  ``logs/``, ``alert.wav`` -- sit next to it. Installed into ``.claude/hooks/``
  this is the same layout the hooks always used.
- ``resolve_project_dir(payload)``: the project the session works on
  (``CLAUDE_PROJECT_DIR`` -> stdin ``cwd`` -> ``git rev-parse --show-toplevel``
  -> the process cwd). Use it for project content such as ``.claude/tasks/``
  or skill roots, never for the hook's own files.
"""

import os
import subprocess
from pathlib import Path


def hook_dir():
    """Directory holding the installed hook file (config/, .env, state/, logs/)."""
    return Path(__file__).resolve().parent


def _git_toplevel():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    top = result.stdout.strip()
    return Path(top) if result.returncode == 0 and top else None


def resolve_project_dir(payload=None):
    """Project root: ``CLAUDE_PROJECT_DIR``, stdin ``cwd``, git top level, then cwd."""
    env_value = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_value:
        return Path(env_value)
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    return _git_toplevel() or Path.cwd()
