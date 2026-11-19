"""Collect Claude Rule files applicable to changed repository paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent_tooling.core.fs_links import find_files
from agent_tooling.core.glob import glob_regex
from agent_tooling.core.paths import normalize_repo_relative_path
from agent_tooling.hooks.common.rules import RuleValidationError, parse_rule


@dataclass
class RuleOriginGroup:
    """A Rule pattern and all changed paths matched by that pattern."""

    pattern: str
    matched_paths: set[str] = field(default_factory=set)

    def as_dict(self) -> dict:
        return {"pattern": self.pattern, "matched_paths": sorted(self.matched_paths)}


@dataclass
class ClaudeRuleSource:
    """One Claude Rule and its matching changed paths grouped by pattern."""

    path: str
    scope: str
    origins: dict[str, RuleOriginGroup] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return "claude_rule"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "path": self.path,
            "scope": self.scope,
            "origins": [self.origins[pattern].as_dict() for pattern in sorted(self.origins)],
        }


def _rule_paths(root: Path) -> list[Path]:
    directory = root / ".claude" / "rules"
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in find_files(directory, "*.md") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def collect_claude_rules(
    root: str | Path,
    changed_paths,
) -> list[ClaudeRuleSource]:
    """Return scoped and always-applied Rules without reading a cache.

    Rules with no ``paths`` key are always applicable. A malformed frontmatter
    raises ``RuleValidationError`` so a broken Rule cannot be silently omitted.
    """
    root = Path(root).resolve()
    changed = sorted(
        {normalize_repo_relative_path(root, raw_path) for raw_path in (changed_paths or ())}
    )
    if not changed:
        return []

    found: list[ClaudeRuleSource] = []
    errors: list[str] = []
    changed_set = set(changed)
    for path in _rule_paths(root):
        relative = path.relative_to(root).as_posix()
        try:
            rule = parse_rule(path, root, require_paths=False)
        except RuleValidationError as exc:
            errors.append(str(exc))
            continue

        source = ClaudeRuleSource(relative, "always" if rule.is_always_applied else "paths")
        if rule.is_always_applied:
            source.origins["<always>"] = RuleOriginGroup("<always>", set(changed))
        else:
            matchers = [(pattern, glob_regex(pattern)) for pattern in rule.paths]
            for pattern, matcher in matchers:
                origin = RuleOriginGroup(pattern)
                origin.matched_paths.update(
                    changed_path for changed_path in changed if matcher.fullmatch(changed_path)
                )
                if origin.matched_paths:
                    source.origins[pattern] = origin

        # A Rule being edited is itself a review candidate even when its own
        # glob does not include ``.claude/rules``.
        if relative in changed_set:
            source.origins.setdefault(
                "<rule-file>", RuleOriginGroup("<rule-file>")
            ).matched_paths.add(relative)
        if source.origins:
            found.append(source)

    if errors:
        raise RuleValidationError("\n".join(errors))
    return found


discover_claude_rules = collect_claude_rules

__all__ = [
    "ClaudeRuleSource",
    "RuleOriginGroup",
    "collect_claude_rules",
    "discover_claude_rules",
]
