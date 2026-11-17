"""Shared fixtures. Tests never read real logs: ``AGENT_LOGS_HOME`` / ``AGENT_LOGS_APPDATA``
point every adapter at a temp copy of ``fixtures/<tool>/`` and per-tool overrides are cleared.

Fixture layout: ``fixtures/<tool>/home/...`` mirrors ``~``, ``fixtures/<tool>/appdata/...``
mirrors ``%APPDATA%``. SQLite databases are never committed: ``<name>.db.sql`` (any depth)
is executed into ``<name>.db`` at the same relative place in the temp copy.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
_CLEARED = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "CLINE_DATA_DIR", "CLINE_DIR")


@pytest.fixture
def fixture_home(tmp_path, monkeypatch):
    """``fixture_home("claude")`` -> temp home path with env pointed at it."""

    def make(tool: str) -> Path:
        src = FIXTURES / tool
        root = tmp_path / "fx"
        if src.is_dir():
            shutil.copytree(src, root, dirs_exist_ok=True)
        home = root / "home"
        appdata = root / "appdata"
        home.mkdir(parents=True, exist_ok=True)
        appdata.mkdir(parents=True, exist_ok=True)
        for key in list(os.environ):
            if key.startswith("AGENT_LOGS_") or key in _CLEARED:
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("AGENT_LOGS_HOME", str(home))
        monkeypatch.setenv("AGENT_LOGS_APPDATA", str(appdata))
        for sql in list(root.rglob("*.sql")):
            dst = sql.with_suffix("")  # foo.db.sql -> foo.db
            conn = sqlite3.connect(dst)
            try:
                conn.executescript(sql.read_text(encoding="utf-8"))
                conn.commit()
            finally:
                conn.close()
            sql.unlink()
        return home

    return make
