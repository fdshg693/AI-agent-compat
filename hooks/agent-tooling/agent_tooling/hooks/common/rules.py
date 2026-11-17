"""Shared Claude Rule parser and scoped-rules data model."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


class RuleValidationError(ValueError):
    """Raised when a Claude Rule does not satisfy the scoped-rules schema."""


@dataclass(frozen=True)
class Rule:
    relative_path: str
    paths: tuple[str, ...]
    body: str
    content_fingerprint: str
    paths_present: bool = True

    @property
    def is_always_applied(self) -> bool:
        return not self.paths_present


@dataclass(frozen=True)
class RuleOrigin:
    rule_path: str
    pattern: str
    matched_path: str


@dataclass(frozen=True)
class MatchedRule:
    """One Rule body selected for injection, with all matching origins."""

    file_path: str
    rule_path: str
    pattern: str
    scenario_id: str
    content_fingerprint: str
    content: str
    origins: tuple[RuleOrigin, ...]

    @property
    def body(self) -> str:
        return self.content

    @property
    def fingerprint(self) -> str:
        return self.content_fingerprint


def _error(path: Path, message: str) -> RuleValidationError:
    return RuleValidationError(f"{path.as_posix()}: {message}")


def _quoted_string(value: str, path: Path) -> str:
    value = value.strip()
    if not value:
        raise _error(path, "paths entries must be strings")
    try:
        if value.startswith('"'):
            parsed = json.loads(value)
        elif value.startswith("'"):
            if not value.endswith("'"):
                raise ValueError
            parsed = value[1:-1].replace("''", "'")
        else:
            plain = value.split(" #", 1)[0].rstrip()
            if re.fullmatch(r"(?:null|true|false|[-+]?\d+(?:\.\d+)?)", plain, re.I):
                raise ValueError
            parsed = plain
    except (ValueError, json.JSONDecodeError):
        raise _error(path, "paths entries must be valid YAML strings")
    if not isinstance(parsed, str) or not parsed:
        raise _error(path, "paths entries must be non-empty strings")
    return parsed


def _inline_paths(value: str, path: Path) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            raise _error(path, "paths must be a YAML list of strings")
    if not isinstance(parsed, list):
        raise _error(path, "paths must be a YAML list of strings")
    values = tuple(
        _quoted_string(json.dumps(item) if isinstance(item, str) else str(item), path)
        for item in parsed
    )
    if not values:
        raise _error(path, "paths must contain at least one pattern")
    return values


def _frontmatter_paths(
    lines: list[str], path: Path, *, require_paths: bool = True
) -> tuple[tuple[str, ...], bool]:
    if not lines or lines[0].strip() != "---":
        raise _error(path, "missing YAML frontmatter")
    closing = next(
        (i for i, line in enumerate(lines[1:], 1) if line.strip() in {"---", "..."}),
        None,
    )
    if closing is None:
        raise _error(path, "unterminated YAML frontmatter")

    paths: list[str] | None = None
    collecting = False
    for line in lines[1:closing]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^\s*paths\s*:(.*)$", line)
        if match:
            if paths is not None:
                raise _error(path, "duplicate paths field")
            value = match.group(1).strip()
            if value:
                paths = list(_inline_paths(value, path))
                collecting = False
            else:
                paths = []
                collecting = True
            continue
        if collecting:
            item = re.match(r"^\s*-\s*(.*?)\s*$", line)
            if item:
                paths.append(_quoted_string(item.group(1), path))
                continue
            if line[:1].isspace():
                raise _error(path, "paths must be a YAML list of strings")
            collecting = False
        if stripped.startswith("-") or ":" not in line:
            raise _error(path, "invalid YAML frontmatter")

    if paths is None and require_paths:
        raise _error(path, "missing required paths field")
    if paths is not None and not paths:
        raise _error(path, "paths must contain at least one pattern")
    return tuple(paths or ()), paths is not None


def parse_rule(
    path: Path,
    root: Path,
    *,
    require_paths: bool = True,
    allow_missing_paths: bool | None = None,
) -> Rule:
    """Parse one Rule file and return content without its frontmatter."""
    if allow_missing_paths is not None:
        require_paths = not allow_missing_paths
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _error(path, f"cannot read Rule: {exc}") from exc
    lines = text.splitlines()
    paths, paths_present = _frontmatter_paths(lines, path, require_paths=require_paths)
    closing = next(i for i, line in enumerate(lines[1:], 1) if line.strip() in {"---", "..."})
    body = "\n".join(lines[closing + 1 :]).strip()
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    fingerprint = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return Rule(relative, paths, body, fingerprint, paths_present)
