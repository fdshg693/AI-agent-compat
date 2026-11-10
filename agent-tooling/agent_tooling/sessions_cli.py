"""Command-line entry point for listing live AI agent sessions.

Reads the per-user registry written by the ``agent_sessions`` hook scenario
(``agent_tooling/core/sessions.py``) and reports which agent tool is running in
which CWD. The default view is live sessions only; ``--all`` includes crashed
remnants and ``--prune`` removes them. ``--watch`` keeps the process alive and
refreshes the view on an interval: on a TTY it redraws in place with ANSI, on a
pipe it appends frames without control characters, and ``--watch --json`` emits
NDJSON (one update per line). This module never imports the hook builder or
generated artifacts.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import sys
import time
from collections.abc import Sequence
from datetime import datetime

from agent_tooling.core import sessions

KNOWN_AGENTS = ("claude", "codex", "cursor", "antigravity", "kilo")
COLUMNS = ("AGENT", "SESSION", "PID", "CWD", "STARTED", "LAST SEEN", "STATE")
DEFAULT_INTERVAL_SECONDS = 3.0
_CLEAR_HOME = "\x1b[H\x1b[J"
_CURSOR_HIDE = "\x1b[?25l"
_CURSOR_SHOW = "\x1b[?25h"
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_STD_OUTPUT_HANDLE = -11


def _positive_interval(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid interval: {value!r}") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("--interval must be greater than 0")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-sessions",
        description="List AI agent sessions registered by the agent_sessions hook.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_stale",
        help="include stale (crashed) sessions in addition to live ones",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="remove stale session files (PID-reuse duplicates are always collapsed)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a stable JSON structure instead of a text table",
    )
    parser.add_argument(
        "--agent",
        default=None,
        help=f"only show one agent tool ({', '.join(KNOWN_AGENTS)})",
    )
    parser.add_argument(
        "-w",
        "--watch",
        action="store_true",
        help="keep running and refresh the view until interrupted",
    )
    parser.add_argument(
        "--interval",
        type=_positive_interval,
        default=DEFAULT_INTERVAL_SECONDS,
        metavar="SECONDS",
        help=f"seconds between refreshes with --watch (default: {DEFAULT_INTERVAL_SECONDS:g})",
    )
    return parser


def _entry_epoch(value):
    if not isinstance(value, str):
        return float("-inf")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("-inf")


def _cleanup_duplicate_pids(target):
    """Delete PID-reuse leftovers, keeping the newest ``last_seen`` per PID.

    Tool-side only; the hooks never call this. A positive PID identifies one
    running process, so entries that share one are older sessions whose ``end``
    never arrived (interrupt, crash) still looking live because the process was
    replaced or reused; only the newest entry can belong to it. Returns the
    number of files removed.
    """
    groups = {}
    try:
        names = sorted(os.listdir(target))
    except OSError:
        return 0
    for name in names:
        if not name.endswith(".json") or name.startswith("."):
            continue
        entry = sessions.read_entry(os.path.join(target, name))
        if entry is None:
            continue
        pid = entry.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            continue
        groups.setdefault(pid, []).append(entry)
    removed = 0
    for items in groups.values():
        if len(items) < 2:
            continue
        items.sort(
            key=lambda entry: (
                _entry_epoch(entry.get("last_seen")),
                _entry_epoch(entry.get("started_at")),
            )
        )
        for entry in items[:-1]:
            if sessions.end_session(entry["agent"], entry["session_id"], directory=target):
                removed += 1
    return removed


def _collect(directory=None):
    """Return readable entries, unreadable names, and removed PID duplicates."""
    target = sessions.registry_dir(directory)
    removed = _cleanup_duplicate_pids(target)
    try:
        names = sorted(os.listdir(target))
    except OSError:
        return [], [], removed
    entries = []
    corrupt = []
    for name in names:
        if not name.endswith(".json") or name.startswith("."):
            continue
        entry = sessions.read_entry(os.path.join(target, name))
        if entry is None:
            corrupt.append(name)
        else:
            entries.append(entry)
    entries.sort(key=lambda item: (item["agent"], item["cwd"], item["started_at"]))
    return entries, corrupt, removed


def _view(entry, *, now=None, ttl=None):
    state = sessions.entry_state(entry, now=now, ttl=ttl)
    return {
        "agent": entry["agent"],
        "session_id": entry["session_id"],
        "pid": entry["pid"],
        "pid_source": entry["pid_source"],
        "cwd": entry["cwd"],
        "started_at": entry["started_at"],
        "last_seen": entry["last_seen"],
        "state": state,
    }


def render_text(views) -> str:
    rows = [COLUMNS]
    for view in views:
        rows.append(
            (
                view["agent"],
                view["session_id"],
                str(view["pid"]) if view["pid"] > 0 else "-",
                view["cwd"],
                view["started_at"],
                view["last_seen"],
                view["state"],
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(COLUMNS))]
    lines = []
    for row in rows:
        cells = [cell.ljust(widths[index]) for index, cell in enumerate(row)]
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)


def render_json(views, *, pruned=None) -> str:
    payload = views if pruned is None else {"sessions": views, "pruned": pruned}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_json_line(views, *, pruned=None) -> str:
    """One compact JSON record per line, for ``--watch --json`` (NDJSON)."""
    payload = views if pruned is None else {"sessions": views, "pruned": pruned}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def render_frame(views, *, pruned=None) -> str:
    """A single watch frame body: table (or empty marker) plus prune count."""
    lines = [render_text([])] if not views else [render_text(views)]
    if not views:
        lines.append("(no active sessions)")
    if pruned:
        lines.append(f"(pruned {pruned} stale session(s))")
    return "\n".join(lines)


def _select_views(entries, args):
    views = []
    for entry in entries:
        if args.agent is not None and entry["agent"] != args.agent:
            continue
        view = _view(entry)
        if view["state"] == "stale" and not args.include_stale:
            continue
        views.append(view)
    return views


def _build_frame(args):
    """Collect, prune and filter one frame. Never raises on unreadable state."""
    entries, corrupt, _ = _collect()
    pruned = None
    if args.prune:
        pruned = sessions.prune()
        entries, _, _ = _collect()
    return _select_views(entries, args), pruned, corrupt


def _enable_virtual_terminal():
    """Enable ANSI processing on Windows terminals; ``True`` elsewhere."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        combined = mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, combined))
    except Exception:
        return False


def _broken_pipe(exc):
    """Detect a closed downstream pipe, including Windows' ``EINVAL``."""
    if isinstance(exc, BrokenPipeError):
        return True
    return sys.platform == "win32" and exc.errno == errno.EINVAL


def _discard_stdout():
    """Point stdout at the null device so shutdown cannot re-raise."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
    except OSError:
        return
    try:
        os.dup2(devnull, sys.stdout.fileno())
    except OSError:
        pass
    finally:
        try:
            os.close(devnull)
        except OSError:
            pass


def _emit(stream, text):
    """Write and flush one chunk; return ``False`` on a closed pipe."""
    try:
        stream.write(text)
        stream.flush()
        return True
    except OSError as exc:
        if not _broken_pipe(exc):
            raise
        if stream is sys.stdout:
            _discard_stdout()
        return False


def run_watch(
    args,
    *,
    interval,
    output=None,
    sleep=None,
    max_frames=None,
    tty=None,
):
    """Refresh the view until interrupted. I/O and timing are injectable."""
    stream = sys.stdout if output is None else output
    wait = time.sleep if sleep is None else sleep
    interactive = stream.isatty() if tty is None else tty
    frames = 0
    try:
        if interactive:
            _emit(stream, _CURSOR_HIDE)
        while True:
            views, pruned, _ = _build_frame(args)
            if args.json:
                text = render_json_line(views, pruned=pruned) + "\n"
            else:
                body = render_frame(views, pruned=pruned)
                text = _CLEAR_HOME + body + "\n" if interactive else body + "\n\n"
            if not _emit(stream, text):
                break
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
            wait(interval)
    finally:
        if interactive:
            _emit(stream, _CURSOR_SHOW)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.watch:
        interactive = sys.stdout.isatty() and _enable_virtual_terminal()
        try:
            return run_watch(args, interval=args.interval, tty=interactive)
        except KeyboardInterrupt:
            return 0

    entries, corrupt, duplicates = _collect()
    for name in corrupt:
        print(f"agent-sessions: skipping unreadable entry: {name}", file=sys.stderr)
    if duplicates:
        print(
            f"agent-sessions: removed {duplicates} duplicate-PID session(s)",
            file=sys.stderr,
        )

    pruned = None
    if args.prune:
        pruned = sessions.prune()
        print(f"agent-sessions: pruned {pruned} stale session(s)", file=sys.stderr)
        entries, _, _ = _collect()

    views = _select_views(entries, args)

    if args.json:
        print(render_json(views, pruned=pruned))
        return 0

    if not views:
        print("(no active sessions)")
        return 0

    print(render_text(views))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "build_parser",
    "main",
    "render_frame",
    "render_json",
    "render_json_line",
    "render_text",
    "run_watch",
]
