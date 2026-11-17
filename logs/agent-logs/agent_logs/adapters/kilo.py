"""Kilo Code (v7, opencode-derived): ``~/.local/share/kilo/kilo.db`` (SQLite, WAL).

Spec: skills/plugins/ai-tools-knowledge/skills/kilo-logs/SKILL.md

- Root: ``AGENT_LOGS_KILO_DIR`` > ``$XDG_DATA_HOME/kilo`` > ``~/.local/share/kilo``; the DB
  is ``<root>/kilo.db`` unless ``KILO_DB`` names an absolute file (the last two env vars
  are ignored when ``AGENT_LOGS_HOME`` makes the run hermetic).
- Opened with ``mode=ro`` (never ``immutable``: rows still in the WAL would be missing).
- Only the ``session``, ``message``, ``part`` and ``project`` tables are ever queried; the
  same DB holds ``account`` / ``credential`` / ``session_share`` secrets. ``auth.json`` is
  never opened. Columns are discovered with ``PRAGMA table_info`` (the schema drifts).
- Listing is a few aggregate queries, filtered in SQL (``--since`` -> ``time_updated``,
  ``--until`` -> ``time_created``) and served by the existing session/message/part
  indexes; message/part bodies are only read by ``iter_events``.
- Session totals come from the cumulative ``session`` columns (``cost`` 0 is kept as a
  recorded 0.0). ``tokens_out`` = output + reasoning. Per-event tokens/cost come from each
  assistant ``message.data`` once (on its first event; ``step-finish`` parts carry no
  tokens to avoid double counting).
- ``message_count`` counts ``message`` rows (user + assistant; one assistant row per
  model step). ``tool_call_count`` counts ``tool`` parts.
- A ``tool`` part holds call and result: it yields a ``tool_call`` and, when output or an
  error is present, a ``tool_result``.
- Sessions with ``parent_id`` (subagent / ``task`` tool) get ``source="subagent"``.
- Project is ``project.worktree`` (``directory`` when the project is ``global``/``/``);
  ``cwd`` is ``session.directory``.
- The VS Code extension's globalStorage is only reported by ``detect()`` (legacy
  Cline-format tasks belong to the cline adapter).
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_logs.adapters.base import Adapter
from agent_logs.model import Event, Filters, Session, SourceInfo
from agent_logs.paths import appdata, home, is_link_like, list_dir, mtime, normalize_path
from agent_logs.readers import dumps_compact, open_sqlite, text_of
from agent_logs.timeutil import parse_ts

# The only tables this adapter may read (everything else may hold secrets).
_TABLES = ("session", "message", "part", "project")
_SESSION_COLS = (
    "id",
    "project_id",
    "parent_id",
    "directory",
    "title",
    "model",
    "cost",
    "tokens_input",
    "tokens_output",
    "tokens_reasoning",
    "tokens_cache_read",
    "tokens_cache_write",
    "time_created",
    "time_updated",
)
_VALID_TOOL = "json_valid(data) AND json_extract(data, '$.type') = 'tool'"


class KiloAdapter(Adapter):
    name = "kilo"
    env_var = "AGENT_LOGS_KILO_DIR"

    def root(self) -> Path:
        env = os.environ.get(self.env_var)
        if env:
            return Path(env)
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg and not os.environ.get("AGENT_LOGS_HOME"):
            return Path(xdg) / "kilo"
        return home() / ".local" / "share" / "kilo"

    def db_path(self) -> Path:
        env = os.environ.get("KILO_DB")
        if (
            env
            and not os.environ.get(self.env_var)
            and not os.environ.get("AGENT_LOGS_HOME")
            and env != ":memory:"
        ):
            p = Path(env)
            return p if p.is_absolute() else self.root() / p
        return self.root() / "kilo.db"

    def _legacy_dir(self) -> Path:
        return appdata() / "Code" / "User" / "globalStorage" / "kilocode.kilo-code"

    def _usable(self, db: Path) -> bool:
        return db.is_file() and not is_link_like(db)

    # ------------------------------------------------------------ discovery

    def detect(self) -> list[SourceInfo]:
        db = self.db_path()
        count = None
        last = None
        if self._usable(db):
            last = max((m for m in (mtime(db), mtime(Path(str(db) + "-wal"))) if m), default=None)
            try:
                with open_sqlite(db, mode="ro") as conn:
                    if "session" in _tables(conn):
                        count = conn.execute("SELECT count(*) FROM session").fetchone()[0]
            except (sqlite3.Error, OSError) as exc:
                self.warn(f"{db}: {exc}")
        out = [
            SourceInfo(
                self.name,
                "db",
                str(db),
                self._usable(db),
                count,
                last,
                note=f"root via {self.env_var} / XDG_DATA_HOME / ~/.local/share/kilo; "
                "only session/message/part/project tables are read",
            )
        ]
        legacy = self._legacy_dir()
        out.append(
            SourceInfo(
                self.name,
                "vscode-globalstorage",
                str(legacy),
                legacy.is_dir(),
                len(list_dir(legacy)) if legacy.is_dir() else None,
                mtime(legacy),
                note="empty in Kilo v7; legacy Cline-format tasks are not read here",
            )
        )
        return out

    # ------------------------------------------------------------ sessions

    def iter_sessions(self, filters: Filters) -> Iterator[Session]:
        db = self.db_path()
        if not self._usable(db):
            return
        try:
            with open_sqlite(db, mode="ro") as conn:
                yield from self._sessions(conn, db, filters)
        except (sqlite3.Error, OSError) as exc:
            self.warn(f"{db}: {exc}")

    def _sessions(self, conn: sqlite3.Connection, db: Path, f: Filters) -> Iterator[Session]:
        tables = _tables(conn)
        if "session" not in tables:
            self.warn(f"{db}: no session table")
            return
        scols = _columns(conn, "session")
        if "id" not in scols:
            self.warn(f"{db}: session table has no id column")
            return
        sel = ", ".join(c if c in scols else f"NULL AS {c}" for c in _SESSION_COLS)
        where, params = [], []
        if f.since and "time_updated" in scols:
            where.append("(time_updated IS NULL OR time_updated >= ?)")
            params.append(_ms(f.since))
        if f.until and "time_created" in scols:
            where.append("(time_created IS NULL OR time_created <= ?)")
            params.append(_ms(f.until))
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(f"SELECT {sel} FROM session{cond} ORDER BY id", params).fetchall()
        if not rows:
            return
        sub = f"SELECT id FROM session{cond}"

        projects: dict[str, str | None] = {}
        if "project" in tables and {"id", "worktree"} <= _columns(conn, "project"):
            projects = dict(conn.execute("SELECT id, worktree FROM project").fetchall())

        msg_stats: dict[str, tuple[int, Any]] = {}
        if "message" in tables:
            mcols = _columns(conn, "message")
            last = "max(time_updated)" if "time_updated" in mcols else "NULL"
            for sid, n, t in conn.execute(
                f"SELECT session_id, count(*), {last} FROM message "
                f"WHERE session_id IN ({sub}) GROUP BY session_id",
                params,
            ):
                msg_stats[sid] = (n, t)

        tool_counts: dict[str, int] = {}
        if "part" in tables:
            tool_counts = dict(
                conn.execute(
                    f"SELECT session_id, count(*) FROM part WHERE session_id IN ({sub}) "
                    f"AND {_VALID_TOOL} GROUP BY session_id",
                    params,
                ).fetchall()
            )

        for r in rows:
            try:
                yield self._session(r, db, projects, msg_stats, tool_counts)
            except Exception as exc:  # noqa: BLE001 - keep listing other sessions
                self.warn(f"{r['id']}: {type(exc).__name__}: {exc}")

    def _session(self, r, db, projects, msg_stats, tool_counts) -> Session:
        sid = r["id"]
        directory = r["directory"] or None
        worktree = projects.get(r["project_id"]) if r["project_id"] else None
        if not worktree or worktree == "/":
            worktree = directory
        n_msgs, last_msg = msg_stats.get(sid, (0, None))
        started = parse_ts(r["time_created"])
        ended = parse_ts(last_msg) or parse_ts(r["time_updated"])
        if started and ended and ended < started:
            ended = started
        model = _loads(r["model"])
        out = _int(r["tokens_output"])
        reasoning = _int(r["tokens_reasoning"])
        if out is not None or reasoning is not None:
            out = (out or 0) + (reasoning or 0)
        cost = r["cost"]
        return Session(
            id=sid,
            tool=self.name,
            source="subagent" if r["parent_id"] else "main",
            project=normalize_path(worktree),
            cwd=directory,
            started_at=started,
            ended_at=ended,
            model=(model.get("id") or model.get("modelID")) if isinstance(model, dict) else None,
            title=r["title"] or None,
            parent_id=r["parent_id"] or None,
            message_count=n_msgs,
            tool_call_count=tool_counts.get(sid, 0),
            tokens_in=_int(r["tokens_input"]),
            tokens_out=out,
            tokens_cache_read=_int(r["tokens_cache_read"]),
            tokens_cache_write=_int(r["tokens_cache_write"]),
            cost=float(cost)
            if isinstance(cost, (int, float)) and not isinstance(cost, bool)
            else None,
            path=str(db),
            ref=(db, sid),
        )

    # ------------------------------------------------------------ events

    def iter_events(self, session: Session) -> Iterator[Event]:
        if isinstance(session.ref, tuple):
            db, sid = session.ref
        else:
            db, sid = Path(session.path or self.db_path()), session.id
        try:
            with open_sqlite(db, mode="ro") as conn:
                tables = _tables(conn)
                if "message" not in tables:
                    return
                has_part = "part" in tables
                msgs = conn.execute(
                    "SELECT id, time_created, data FROM message WHERE session_id = ? "
                    "ORDER BY time_created, id",
                    (sid,),
                ).fetchall()
                for m in msgs:
                    parts = []
                    if has_part:
                        parts = conn.execute(
                            "SELECT id, time_created, data FROM part WHERE message_id = ? "
                            "ORDER BY id",
                            (m["id"],),
                        ).fetchall()
                    yield from self._message_events(sid, m, parts)
        except (sqlite3.Error, OSError) as exc:
            self.warn(f"{sid}: {exc}")

    def _message_events(self, sid: str, m, parts) -> Iterator[Event]:
        data = _loads(m["data"])
        if not isinstance(data, dict):
            yield Event(
                session_id=sid,
                tool=self.name,
                ts=parse_ts(m["time_created"]),
                kind="raw",
                raw=m["data"],
            )
            return
        role = data.get("role")
        mts = parse_ts((data.get("time") or {}).get("created")) or parse_ts(m["time_created"])
        assistant = role == "assistant"
        model = data.get("modelID") if assistant else None
        events: list[Event] = []
        for p in parts:
            pdata = _loads(p["data"])
            events.extend(self._part_events(sid, role, model, mts, p, pdata))
        if assistant and ("tokens" in data or "cost" in data):
            tok = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
            cache = tok.get("cache") if isinstance(tok.get("cache"), dict) else {}
            out, reasoning = _int(tok.get("output")), _int(tok.get("reasoning"))
            if out is not None or reasoning is not None:
                out = (out or 0) + (reasoning or 0)
            cost = data.get("cost")
            usage = dict(
                tokens_in=_int(tok.get("input")),
                tokens_out=out,
                tokens_cache_read=_int(cache.get("read")),
                tokens_cache_write=_int(cache.get("write")),
                cost=float(cost)
                if isinstance(cost, (int, float)) and not isinstance(cost, bool)
                else None,
            )
            if not events:
                events.append(
                    Event(
                        session_id=sid,
                        tool=self.name,
                        ts=mts,
                        role="assistant",
                        kind="usage",
                        model=model,
                        raw=data,
                    )
                )
            for k, v in usage.items():
                setattr(events[0], k, v)
        if assistant and isinstance(data.get("error"), dict):
            err = data["error"]
            edata = err.get("data") if isinstance(err.get("data"), dict) else {}
            msg = text_of(edata.get("message"))
            events.append(
                Event(
                    session_id=sid,
                    tool=self.name,
                    ts=mts,
                    role="system",
                    kind="system",
                    text=": ".join(x for x in (err.get("name"), msg) if x) or "error",
                    raw=data,
                )
            )
        yield from events

    def _part_events(self, sid, role, model, mts, p, d) -> Iterator[Event]:
        ts_default = parse_ts(p["time_created"]) or mts
        if not isinstance(d, dict):
            yield Event(session_id=sid, tool=self.name, ts=ts_default, kind="raw", raw=p["data"])
            return
        t = d.get("type")
        tm = d.get("time") if isinstance(d.get("time"), dict) else {}
        ts = parse_ts(tm.get("start")) or ts_default
        r = role if role in ("user", "assistant") else None
        base = dict(session_id=sid, tool=self.name, model=model, raw=d)
        if t == "text":
            synthetic = bool(d.get("synthetic")) or bool(d.get("ignored"))
            yield Event(
                ts=ts,
                role="system" if synthetic else r,
                kind="system" if synthetic else "message",
                text=text_of(d.get("text")),
                **base,
            )
        elif t == "reasoning":
            yield Event(ts=ts, role=r, kind="reasoning", text=text_of(d.get("text")), **base)
        elif t == "tool":
            st = d.get("state") if isinstance(d.get("state"), dict) else {}
            stm = st.get("time") if isinstance(st.get("time"), dict) else {}
            name, cid = d.get("tool"), d.get("callID")
            inp = st.get("input")
            yield Event(
                ts=parse_ts(stm.get("start")) or ts,
                role=r or "assistant",
                kind="tool_call",
                tool_name=name,
                call_id=cid,
                text=dumps_compact(inp) if inp is not None else None,
                **base,
            )
            out = st.get("output")
            if out is None and st.get("error") is not None:
                out = st.get("error")
            if out is not None:
                yield Event(
                    ts=parse_ts(stm.get("end")) or parse_ts(stm.get("start")) or ts,
                    role="tool",
                    kind="tool_result",
                    tool_name=name,
                    call_id=cid,
                    text=text_of(out),
                    **base,
                )
        elif t == "step-start":
            return
        elif t == "step-finish":
            yield Event(
                ts=parse_ts(tm.get("end")) or ts,
                role=None,
                kind="turn_end",
                text=d.get("reason"),
                **base,
            )
        elif t == "patch":
            files = d.get("files") if isinstance(d.get("files"), list) else []
            yield Event(
                ts=ts,
                role="system",
                kind="system",
                text="patch: " + ", ".join(str(x) for x in files),
                **base,
            )
        elif t == "file":
            # url may be a data: URL carrying the whole file; never used as text
            yield Event(
                ts=ts,
                role=r,
                kind="message",
                text=f"[file] {d.get('filename') or d.get('mime') or ''}".strip(),
                **base,
            )
        elif t in ("compaction", "summary"):
            yield Event(ts=ts, role="system", kind="summary", text=text_of(d.get("text")), **base)
        else:
            yield Event(ts=ts, role=r, kind="raw", **base)


def _tables(conn: sqlite3.Connection) -> set[str]:
    """Names of the allowed tables that exist (only ``sqlite_master`` is consulted)."""
    marks = ",".join("?" * len(_TABLES))
    return {
        r[0]
        for r in conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name IN ({marks})", _TABLES
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    assert table in _TABLES
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _loads(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _int(v) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
