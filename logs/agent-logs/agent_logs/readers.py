"""Low-level, read-only readers: streaming JSON Lines, JSON files, SQLite.

Nothing here writes next to the source files except what SQLite itself may do
for ``mode=ro`` on a WAL database; adapters that must avoid even that use
``open_sqlite(..., mode="copy")``.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import warnings
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote


def iter_jsonl(
    path: Path, *, skip_if_contains: Iterable[str] = (), max_line_bytes: int | None = None
) -> Iterator[dict[str, Any]]:
    """Yield JSON objects line by line. Broken lines (e.g. a half-written last line)
    and non-object lines are skipped. Lines containing any ``skip_if_contains``
    substring are dropped before parsing (cheap filter for huge record types)."""
    skips = tuple(skip_if_contains)
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            if max_line_bytes is not None and len(line) > max_line_bytes:
                continue
            if skips and any(s in line for s in skips):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def read_json(path: Path) -> Any:
    """Parse a whole JSON file; ``None`` when missing or broken."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def sqlite_uri(path: Path, *, immutable: bool = False) -> str:
    p = Path(path).resolve().as_posix()
    if not p.startswith("/"):
        p = "/" + p  # Windows drive path -> file:///C:/...
    q = "mode=ro" + ("&immutable=1" if immutable else "")
    return f"file://{quote(p, safe='/:')}?{q}"


@contextmanager
def open_sqlite(path: Path, *, mode: str = "ro") -> Iterator[sqlite3.Connection]:
    """Open a SQLite database without modifying it.

    - ``ro``: ``file:...?mode=ro`` URI; falls back to ``copy`` if that fails.
    - ``copy``: copy the db plus ``-wal``/``-shm`` to a temp dir and read the copy
      (reads WAL content, never touches the original's directory).
    - ``immutable``: ``mode=ro&immutable=1``; skips the WAL, so recent rows may be missing.
    """
    conn: sqlite3.Connection | None = None
    tmp: tempfile.TemporaryDirectory | None = None
    try:
        if mode in ("ro", "immutable"):
            try:
                conn = sqlite3.connect(sqlite_uri(path, immutable=mode == "immutable"), uri=True)
                conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
                if mode == "immutable":
                    warnings.warn(
                        f"{path}: opened immutable; rows still in the WAL are not visible",
                        stacklevel=3,
                    )
            except sqlite3.Error:
                if conn is not None:
                    conn.close()
                conn = None
                mode = "copy"
        if conn is None:
            tmp = tempfile.TemporaryDirectory(prefix="agent-logs-")
            dst = Path(tmp.name) / Path(path).name
            shutil.copy2(path, dst)
            for suffix in ("-wal", "-shm"):
                side = Path(str(path) + suffix)
                if side.exists():
                    shutil.copy2(side, Path(str(dst) + suffix))
            conn = sqlite3.connect(str(dst))
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        if conn is not None:
            conn.close()
        if tmp is not None:
            tmp.cleanup()


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def text_of(value: Any, *, limit: int | None = None) -> str | None:
    """Flatten common content shapes (str / list of blocks / dict) into plain text."""
    if value is None:
        return None
    if isinstance(value, str):
        out = value
    elif isinstance(value, list):
        parts = [text_of(v) for v in value]
        out = "\n".join(p for p in parts if p)
    elif isinstance(value, dict):
        for key in ("text", "content", "output", "thinking", "message", "value"):
            if key in value and value[key] is not None:
                return text_of(value[key], limit=limit)
        out = json.dumps(value, ensure_ascii=False)
    else:
        out = str(value)
    if limit is not None and len(out) > limit:
        out = out[:limit]
    return out or None


def dumps_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
