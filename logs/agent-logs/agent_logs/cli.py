"""``agent-logs``: read-only search and stats over local AI coding agent logs.

Subcommands: sources / sessions / show / search / stats. Human tables by default;
``--json`` emits NDJSON for list-like output (sources, sessions, show, search) and
one JSON object for ``stats``. Adapter problems go to stderr as warnings and never
abort the other tools.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

from agent_logs import __version__
from agent_logs.adapters import TOOL_NAMES, load_many
from agent_logs.adapters.base import Adapter
from agent_logs.model import KINDS, ROLES, Filters
from agent_logs.query import Matcher, find_session, iter_events, iter_sessions, search
from agent_logs.stats import GROUP_KEYS, aggregate, totals
from agent_logs.timeutil import parse_cli_time


def _tools_arg(value: str) -> list[str]:
    names = [v.strip() for v in value.split(",") if v.strip()]
    bad = [n for n in names if n not in TOOL_NAMES]
    if bad:
        raise argparse.ArgumentTypeError(
            f"unknown tool(s): {', '.join(bad)} (choose from {', '.join(TOOL_NAMES)})"
        )
    return names


def _time_arg(value: str) -> datetime:
    try:
        return parse_cli_time(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _common(p: argparse.ArgumentParser, *, role: bool = False) -> None:
    g = p.add_argument_group("filters")
    g.add_argument("--tool", type=_tools_arg, help=f"comma list: {','.join(TOOL_NAMES)}")
    g.add_argument("--since", type=_time_arg, help="ISO date/time or relative (30m, 12h, 7d, 2w)")
    g.add_argument("--until", type=_time_arg, help="ISO date/time or relative")
    g.add_argument("--project", help="case-insensitive substring of the project path")
    if role:
        g.add_argument("--role", choices=ROLES, help="only events with this role")
    p.add_argument("--json", action="store_true", help="machine-readable output (NDJSON)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-logs",
        description="Search and aggregate local AI coding agent logs (read-only).",
    )
    parser.add_argument("--version", action="version", version=f"agent-logs {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sources", help="where each tool's logs live and what was found")
    p.add_argument("--tool", type=_tools_arg)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("sessions", help="list sessions (newest first)")
    _common(p)
    p.add_argument("-n", "--limit", type=int, default=50, help="max rows (0 = all, default 50)")
    p.add_argument("--wide", action="store_true", help="show project and title columns in full")

    p = sub.add_parser("show", help="print one session's normalized events")
    p.add_argument("session", help="session id, unique id prefix, or <tool>:<id>")
    p.add_argument("--tool", type=_tools_arg, help="limit the lookup to these tools")
    p.add_argument("--role", choices=ROLES)
    p.add_argument("--kind", help=f"comma list of event kinds ({','.join(KINDS)})")
    p.add_argument("--raw", action="store_true", help="include the original record (--json)")
    p.add_argument("--full", action="store_true", help="do not truncate text")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("search", help="search message text and tool calls")
    p.add_argument("query")
    _common(p, role=True)
    p.add_argument("-e", "--regex", action="store_true", help="treat query as a regex")
    p.add_argument("-s", "--case-sensitive", action="store_true")
    p.add_argument("--kind", help=f"comma list of event kinds ({','.join(KINDS)})")
    p.add_argument("-n", "--limit", type=int, default=100, help="max hits (0 = all)")
    p.add_argument("--width", type=int, default=120, help="snippet width in characters")

    p = sub.add_parser("stats", help="aggregate counts / tokens / cost")
    _common(p)
    p.add_argument("--by", choices=GROUP_KEYS, default="tool", help="group key (default tool)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    adapters, load_errors = load_many(getattr(args, "tool", None))
    filters = Filters(
        tools=getattr(args, "tool", None),
        since=getattr(args, "since", None),
        until=getattr(args, "until", None),
        project=getattr(args, "project", None),
        role=getattr(args, "role", None),
    )
    try:
        code = _COMMANDS[args.command](args, adapters, filters)
    except BrokenPipeError:
        code = 0
    except KeyboardInterrupt:
        code = 130
    for msg in load_errors + [w for a in adapters for w in a.warnings]:
        print(f"warning: {msg}", file=sys.stderr)
    return code


# ---------------------------------------------------------------- commands

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def cmd_sources(args, adapters: list[Adapter], _f: Filters) -> int:
    rows = []
    for a in adapters:
        try:
            rows.extend(a.detect())
        except Exception as exc:  # noqa: BLE001
            a.warn(f"detect failed ({type(exc).__name__}: {exc})")
    if args.json:
        _ndjson(r.to_dict() for r in rows)
        return 0
    _table(
        ("TOOL", "SOURCE", "FOUND", "COUNT", "LAST MODIFIED", "PATH", "NOTE"),
        (
            (
                r.tool,
                r.source,
                "yes" if r.exists else "-",
                "" if r.count is None else r.count,
                _fmt_time(r.last_modified),
                r.path,
                r.note or "",
            )
            for r in rows
        ),
    )
    return 0


def cmd_sessions(args, adapters, f: Filters) -> int:
    sessions = sorted(
        iter_sessions(adapters, f),
        key=lambda s: s.ended_at or s.started_at or _EPOCH,
        reverse=True,
    )
    if args.limit:
        sessions = sessions[: args.limit]
    if args.json:
        _ndjson(s.to_dict() for s in sessions)
        return 0
    w = None if args.wide else 40
    _table(
        (
            "TOOL",
            "SOURCE",
            "SESSION",
            "STARTED",
            "ENDED",
            "MSGS",
            "TOOLS",
            "MODEL",
            "PROJECT",
            "TITLE",
        ),
        (
            (
                s.tool,
                s.source or "",
                s.id,
                _fmt_time(s.started_at),
                _fmt_time(s.ended_at),
                _num(s.message_count),
                _num(s.tool_call_count),
                s.model or "",
                _trim(s.project or s.cwd or "", w, left=True),
                _trim(s.title or "", w),
            )
            for s in sessions
        ),
    )
    return 0


def cmd_show(args, adapters, f: Filters) -> int:
    try:
        found = find_session(adapters, args.session)
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not found:
        print(f"error: session not found: {args.session}", file=sys.stderr)
        return 1
    adapter, s = found
    kinds = _kinds(args.kind)
    events = [
        e for e in iter_events(adapter, s, Filters(role=args.role)) if not kinds or e.kind in kinds
    ]
    if args.json:
        _ndjson(e.to_dict(include_raw=args.raw) for e in events)
        return 0
    print(f"# {s.tool}:{s.id}  {s.source or ''}  {s.project or s.cwd or ''}")
    if s.title:
        print(f"# {s.title}")
    for e in events:
        label = e.kind if e.kind != "message" else (e.role or "message")
        if e.tool_name:
            label += f" {e.tool_name}"
        text = e.text or ""
        if not args.full:
            text = _trim(text.replace("\r", ""), 600)
        tok = ""
        if e.tokens_in is not None or e.tokens_out is not None:
            tok = f"  [in={_num(e.tokens_in)} out={_num(e.tokens_out)}]"
        print(f"\n[{_fmt_time(e.ts)}] {label}{tok}")
        if text:
            print("  " + text.replace("\n", "\n  "))
    return 0


def cmd_search(args, adapters, f: Filters) -> int:
    try:
        matcher = Matcher(args.query, regex=args.regex, case_sensitive=args.case_sensitive)
    except Exception as exc:  # re.error
        print(f"error: invalid pattern: {exc}", file=sys.stderr)
        return 2
    hits = search(adapters, f, matcher, kinds=_kinds(args.kind), width=args.width)
    n = 0
    rows = []
    for h in hits:
        n += 1
        if args.json:
            d = h.event.to_dict()
            d["text"] = h.snippet
            d["project"] = h.session.project
            print(json.dumps(d, ensure_ascii=False), flush=False)
        else:
            rows.append(h)
        if args.limit and n >= args.limit:
            break
    if not args.json:
        for h in rows:
            e = h.event
            label = e.kind if e.kind != "message" else (e.role or "message")
            if e.tool_name:
                label += f" {e.tool_name}"
            print(f"{e.tool}:{e.session_id}  {_fmt_time(e.ts)}  {label}")
            print(f"  {h.snippet}")
        if args.limit and n >= args.limit:
            print(f"(stopped at --limit {args.limit})", file=sys.stderr)
    return 0 if n else 1


def cmd_stats(args, adapters, f: Filters) -> int:
    buckets = aggregate(adapters, f, args.by)
    total = totals(buckets)
    if args.json:
        print(
            json.dumps(
                {"by": args.by, "rows": [b.to_dict() for b in buckets], "total": total.to_dict()},
                ensure_ascii=False,
            )
        )
        return 0
    head = (
        args.by.upper(),
        "SESSIONS",
        "MSGS",
        "TOOL CALLS",
        "IN",
        "OUT",
        "CACHE R",
        "CACHE W",
        "COST $",
    )
    _table(
        head,
        (
            (
                _trim(b.key, 60, left=True),
                _num(b.sessions),
                _num(b.messages) if args.by != "tool-name" else "",
                _num(b.tool_calls),
                _num(b.tokens_in),
                _num(b.tokens_out),
                _num(b.tokens_cache_read),
                _num(b.tokens_cache_write),
                "" if b.cost is None else f"{b.cost:.2f}",
            )
            for b in [*buckets, total]
        ),
    )
    return 0


_COMMANDS = {
    "sources": cmd_sources,
    "sessions": cmd_sessions,
    "show": cmd_show,
    "search": cmd_search,
    "stats": cmd_stats,
}

# ---------------------------------------------------------------- formatting


def _kinds(value: str | None) -> set[str] | None:
    return {k.strip() for k in value.split(",") if k.strip()} if value else None


def _ndjson(items: Iterable[dict]) -> None:
    for d in items:
        sys.stdout.write(json.dumps(d, ensure_ascii=False) + "\n")


def _fmt_time(dt: datetime | None) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M") if dt else ""


def _num(v) -> str:
    return "" if v is None else f"{v:,}" if isinstance(v, int) else str(v)


def _trim(s: str, width: int | None, *, left: bool = False) -> str:
    s = s.replace("\n", " ") if width and width < 200 else s
    if width is None or len(s) <= width:
        return s
    return "…" + s[-(width - 1) :] if left else s[: width - 1] + "…"


def _table(head: Sequence[str], rows: Iterable[Sequence]) -> None:
    data = [[str(c) for c in r] for r in rows]
    widths = [len(h) for h in head]
    for r in data:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*head).rstrip())
    for r in data:
        print(fmt.format(*r).rstrip())


if __name__ == "__main__":
    sys.exit(main())
