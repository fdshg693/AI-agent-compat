"""Command-line entry point for the advisory agent-context-check command."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from agent_tooling.checks.agent_context import (
    ContextCheckError,
    ContextReport,
    ExplainReport,
    check_staged_context,
    explain_context,
)
from agent_tooling.hooks.common.rules import RuleValidationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-context-check",
        description="List AGENTS.md and Claude Rule sources applicable to staged changes.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        required=True,
        help="inspect only paths staged in the Git index",
    )
    try:
        package_version = version("agent-tooling")
    except PackageNotFoundError:
        package_version = "0.1.0"
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version}")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    return parser


def render_text(report: ContextReport) -> str:
    """Render a stable, human-oriented report."""
    lines = ["Changed paths:"]
    if report.changes:
        for change in report.changes:
            if change.old_path is not None:
                lines.append(f"  - {change.old_path} -> {change.path} ({change.status})")
            else:
                lines.append(f"  - {change.path} ({change.status})")
    else:
        lines.append("  (none)")

    lines.append("Context sources:")
    if not report.sources:
        lines.append("  (none)")
        return "\n".join(lines)

    for source in report.sources:
        lines.append(f"  - {source.kind}: {source.path} (scope: {source.scope})")
        if hasattr(source, "matched_paths"):
            matched_paths = sorted(source.matched_paths)
            lines.extend(f"      matched: {path}" for path in matched_paths)
        else:
            for origin in source.as_dict()["origins"]:
                lines.append(f"      pattern {origin['pattern']}:")
                lines.extend(f"        - {path}" for path in origin["matched_paths"])
    return "\n".join(lines)


def render_json(report: ContextReport) -> str:
    """Render the machine-readable report."""
    return json.dumps(report.as_dict(), ensure_ascii=False, indent=2)


def render_explain_text(report: ExplainReport) -> str:
    """Render candidate sources and why each applies to one target."""
    data = report.as_dict()
    lines = [f"Target: {data['target']}", "Context candidates:"]
    if not data["sources"]:
        lines.append("  (none)")
    else:
        for source in data["sources"]:
            lines.append(f"  - {source['kind']}: {source['path']}")
            lines.append(f"      reason: {source['reason']}")
    lines.append(
        "This is a candidate list; it does not reproduce tool-specific injection order or prompts."
    )
    return "\n".join(lines)


def build_explain_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-context-check explain",
        description="List context candidates applicable to one repository file.",
    )
    parser.add_argument("path", help="file path, relative to the invocation directory or absolute")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "explain":
        args = build_explain_parser().parse_args(arguments[1:])
        try:
            report = explain_context(Path.cwd(), args.path)
        except (ContextCheckError, RuleValidationError, OSError, ValueError) as exc:
            print(f"agent-context-check explain: {exc}", file=sys.stderr)
            return 1
        output = (
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2)
            if args.format == "json"
            else render_explain_text(report)
        )
        print(output)
        return 0

    parser = build_parser()
    args = parser.parse_args(arguments)
    try:
        report = check_staged_context()
    except (ContextCheckError, RuleValidationError, OSError, ValueError) as exc:
        print(f"agent-context-check: {exc}", file=sys.stderr)
        return 1

    output = render_json(report) if args.format == "json" else render_text(report)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_explain_parser",
    "build_parser",
    "main",
    "render_explain_text",
    "render_json",
    "render_text",
]
