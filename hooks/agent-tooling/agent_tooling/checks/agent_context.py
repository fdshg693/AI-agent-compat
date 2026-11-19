"""Build an advisory context-coverage report from the staged Git index."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent_tooling.core.fs_links import find_files
from agent_tooling.core.paths import normalize_repo_relative_path
from agent_tooling.sources.agents_md import AgentsMdSource, collect_agents_md
from agent_tooling.sources.claude_rules import ClaudeRuleSource, collect_claude_rules


class ContextCheckError(RuntimeError):
    """Raised when the staged context cannot be inspected."""


@dataclass(frozen=True)
class StagedChange:
    """One path record returned by the staged Git diff."""

    status: str
    path: str
    old_path: str | None = None

    @property
    def is_rename(self) -> bool:
        return self.old_path is not None

    def as_dict(self) -> dict:
        result = {"status": self.status, "path": self.path}
        if self.old_path is not None:
            result["old_path"] = self.old_path
        return result


@dataclass(frozen=True)
class ContextReport:
    """Deterministic changed-path and context-source report."""

    changes: tuple[StagedChange, ...]
    sources: tuple[AgentsMdSource | ClaudeRuleSource, ...]

    @property
    def changed_paths(self) -> tuple[str, ...]:
        paths = {change.path for change in self.changes}
        paths.update(change.old_path for change in self.changes if change.old_path is not None)
        return tuple(sorted(paths))

    def as_dict(self) -> dict:
        return {
            "changed_paths": list(self.changed_paths),
            "changes": [change.as_dict() for change in self.changes],
            "sources": [source.as_dict() for source in self.sources],
        }


@dataclass(frozen=True)
class ExplainReport:
    """Applicable context sources for one repository file path."""

    target: str
    sources: tuple[AgentsMdSource | ClaudeRuleSource, ...]

    def as_dict(self) -> dict:
        candidates = []
        for source in self.sources:
            candidate = source.as_dict()
            if isinstance(source, AgentsMdSource):
                candidate["reason"] = f"ancestor scope: {source.scope}"
            else:
                reasons = []
                for origin in source.as_dict()["origins"]:
                    pattern = origin["pattern"]
                    if pattern == "<always>":
                        reasons.append("always-applied Rule")
                    elif pattern == "<rule-file>":
                        reasons.append("Rule file is the target")
                    else:
                        reasons.append(f"matches path pattern: {pattern}")
                candidate["reason"] = "; ".join(reasons)
            candidates.append(candidate)
        return {"target": self.target, "sources": candidates}


def git_repository_root(start: str | Path | None = None) -> Path:
    """Resolve the Git worktree root or raise a user-facing error."""
    cwd = Path(start or Path.cwd()).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a Git repository"
        raise ContextCheckError(f"cannot find Git repository: {detail}")
    return Path(result.stdout.strip()).resolve()


def _decode_git_path(raw: bytes) -> str:
    return os.fsdecode(raw).replace("\\", "/")


def _parse_name_status_z(raw: bytes) -> list[StagedChange]:
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    changes: list[StagedChange] = []
    index = 0
    while index < len(fields):
        status = fields[index].decode("ascii", errors="replace")
        index += 1
        kind = status[:1]
        if kind in {"R", "C"}:
            if index + 1 >= len(fields):
                raise ContextCheckError("Git returned an incomplete rename/copy record")
            old_path = _decode_git_path(fields[index])
            new_path = _decode_git_path(fields[index + 1])
            index += 2
            changes.append(StagedChange(status, new_path, old_path))
        else:
            if index >= len(fields):
                raise ContextCheckError("Git returned an incomplete staged path record")
            changes.append(StagedChange(status, _decode_git_path(fields[index])))
            index += 1
    return sorted(changes, key=lambda change: (change.path, change.old_path or "", change.status))


def staged_changes(root: str | Path) -> list[StagedChange]:
    """Read added, changed, deleted, and renamed paths from the Git index."""
    root = Path(root).resolve()
    result = subprocess.run(
        [
            "git",
            "diff",
            "-M",
            "--name-status",
            "--cached",
            "-z",
            "--diff-filter=ACDMRTUXB",
            "--",
        ],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = os.fsdecode(result.stderr).strip() or "git diff failed"
        raise ContextCheckError(f"cannot read staged changes: {detail}")
    try:
        return _parse_name_status_z(result.stdout)
    except (UnicodeError, ValueError) as exc:
        raise ContextCheckError(f"cannot parse staged changes: {exc}") from exc


def build_context_report(root: str | Path, changes: list[StagedChange]) -> ContextReport:
    """Collect all applicable sources for the supplied staged changes."""
    changed_paths = []
    normalized_changes = []
    for change in changes:
        path = normalize_repo_relative_path(root, change.path)
        old_path = (
            normalize_repo_relative_path(root, change.old_path)
            if change.old_path is not None
            else None
        )
        normalized_changes.append(StagedChange(change.status, path, old_path))
        changed_paths.append(path)
        if old_path is not None:
            changed_paths.append(old_path)
    agents = collect_agents_md(root, changed_paths)
    rules = collect_claude_rules(root, changed_paths)
    sources = tuple(
        sorted(
            [*agents, *rules],
            key=lambda source: (
                0 if isinstance(source, AgentsMdSource) else 1,
                source.scope.count("/") if isinstance(source, AgentsMdSource) else 0,
                source.path,
            ),
        )
    )
    return ContextReport(tuple(normalized_changes), sources)


def check_staged_context(start: str | Path | None = None) -> ContextReport:
    """Resolve the repository, inspect its index, and build a report."""
    root = git_repository_root(start)
    return build_context_report(root, staged_changes(root))


def explain_context(
    start: str | Path | None,
    path: str | Path,
) -> ExplainReport:
    """Explain context candidates for a file without consulting the Git index."""
    cwd = Path(start or Path.cwd()).resolve()
    root = git_repository_root(cwd)
    raw_path = Path(path)
    candidate = (raw_path if raw_path.is_absolute() else cwd / raw_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"path is outside repository: {path}")
    if candidate.is_dir():
        raise ValueError(f"path must be a file, not a directory: {path}")

    # Rule parsing reads files, so reject external symlink sources before collection.
    rules_dir = root / ".claude" / "rules"
    if rules_dir.is_dir():
        for rule_path in find_files(rules_dir, "*.md"):
            resolved = rule_path.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError(f"context source is outside repository: {rule_path}")

    relative_path = candidate.relative_to(root).as_posix()
    agents = collect_agents_md(root, [relative_path])
    for source in agents:
        source_path = (root / source.path).resolve()
        if not source_path.is_relative_to(root):
            raise ValueError(f"context source is outside repository: {source.path}")
    rules = collect_claude_rules(root, [relative_path])
    sources = tuple(
        sorted(
            [*agents, *rules],
            key=lambda source: (
                0 if isinstance(source, AgentsMdSource) else 1,
                source.scope.count("/") if isinstance(source, AgentsMdSource) else 0,
                source.path,
            ),
        )
    )
    return ExplainReport(relative_path, sources)


# Short aliases make the source useful to callers embedding the command.
collect_staged_changes = staged_changes
build_report = build_context_report

__all__ = [
    "ContextCheckError",
    "ContextReport",
    "ExplainReport",
    "StagedChange",
    "build_context_report",
    "build_report",
    "check_staged_context",
    "explain_context",
    "collect_staged_changes",
    "git_repository_root",
    "staged_changes",
]
