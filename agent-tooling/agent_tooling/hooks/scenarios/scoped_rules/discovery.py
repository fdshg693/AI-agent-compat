"""Discover Claude Rules that apply to concrete touched file paths."""

from __future__ import annotations

import re
from pathlib import Path

from agent_tooling.core.fs_links import find_files
from agent_tooling.core.glob import glob_regex, match_path
from agent_tooling.core.paths import normalize_repo_relative_path
from .definition import FILE_REGEXES, RULES_DIRECTORY, SCENARIO_ID
from .cache import CACHE_NAME, cache_key, load_emitted, save_emitted
from .rules import MatchedRule, RuleOrigin, RuleValidationError, parse_rule

__all__ = ["compile_file_regexes", "discover_scoped_rules", "match_path", "validate_rules"]


def _compile_regexes(file_regexes: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    compiled = []
    for expression in file_regexes:
        if not isinstance(expression, str):
            raise RuleValidationError("FILE_REGEXES entries must be strings")
        try:
            compiled.append(re.compile(expression))
        except re.error as exc:
            raise RuleValidationError(f"invalid regex {expression!r}: {exc}") from exc
    return tuple(compiled)


def compile_file_regexes(file_regexes: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """Compile the optional technical filters, reporting invalid patterns."""
    return _compile_regexes(file_regexes)


def _rule_paths(root: Path) -> list[Path]:
    directory = root / RULES_DIRECTORY
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in find_files(directory, "*.md") if path.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    )


def discover_scoped_rules(
    root: Path,
    touched_paths,
    *,
    session_id: str,
    file_regexes: tuple[str, ...] | None = None,
    cache_name: str = CACHE_NAME,
) -> list[MatchedRule]:
    """Return each newly applicable Rule once, in deterministic order.

    Rule globs are evaluated directly against the supplied paths, including
    paths that do not exist yet (for example an Add File patch).
    """
    root = Path(root).resolve()
    expressions = FILE_REGEXES if file_regexes is None else file_regexes
    regexes = _compile_regexes(tuple(expressions))
    touched = set()
    for raw_path in touched_paths or ():
        try:
            touched.add(normalize_repo_relative_path(root, raw_path))
        except ValueError:
            continue
    if not touched:
        return []

    cache_path, emitted = load_emitted(session_id, cache_name)
    found: list[MatchedRule] = []
    for path in _rule_paths(root):
        rule = parse_rule(path, root)
        origins: list[RuleOrigin] = []
        matchers = [(pattern, glob_regex(pattern)) for pattern in rule.paths]
        for touched_path in sorted(touched):
            if not all(regex.fullmatch(touched_path) for regex in regexes):
                continue
            for pattern, matcher in matchers:
                if matcher.fullmatch(touched_path):
                    origins.append(RuleOrigin(rule.relative_path, pattern, touched_path))
        if not origins:
            continue
        key = cache_key(rule.relative_path, rule.content_fingerprint)
        if key in emitted:
            continue
        emitted.add(key)
        origins.sort(key=lambda origin: (origin.matched_path, origin.pattern))
        found.append(
            MatchedRule(
                file_path=origins[0].matched_path,
                rule_path=rule.relative_path,
                pattern=origins[0].pattern,
                scenario_id=SCENARIO_ID,
                content_fingerprint=rule.content_fingerprint,
                content=rule.body,
                origins=tuple(origins),
            )
        )
    save_emitted(cache_path, emitted)
    return found


def validate_rules(root: Path) -> list:
    """Validate every Rule file, raising one error that names all failures."""
    errors = []
    for path in _rule_paths(Path(root).resolve()):
        try:
            parse_rule(path, Path(root).resolve())
        except RuleValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise RuleValidationError("\n".join(errors))
    return [
        path.relative_to(Path(root).resolve()).as_posix()
        for path in _rule_paths(Path(root).resolve())
    ]
