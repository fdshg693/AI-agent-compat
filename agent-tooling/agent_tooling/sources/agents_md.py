"""Collect the AGENTS.md files in scope for changed repository paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agent_tooling.core.discovery import ancestor_chain
from agent_tooling.core.paths import normalize_repo_relative_path


CANDIDATE_NAMES = ("AGENTS.override.md", "AGENTS.md")


@dataclass
class AgentsMdSource:
    """One AGENTS file and the changed paths to which its directory applies."""

    path: str
    scope: str
    matched_paths: set[str] = field(default_factory=set)

    @property
    def kind(self) -> str:
        return "agents_md"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "path": self.path,
            "scope": self.scope,
            "matched_paths": sorted(self.matched_paths),
        }


def _path_directory(root: Path, relative_path: str) -> Path:
    return (root / relative_path).parent


def collect_agents_md(
    root: str | Path,
    changed_paths,
    *,
    candidate_names: tuple[str, ...] = CANDIDATE_NAMES,
) -> list[AgentsMdSource]:
    """Return all applicable AGENTS files, ordered from root to leaves.

    An ``AGENTS.override.md`` takes precedence over ``AGENTS.md`` in the same
    directory, matching the nested-agents hook's input contract.
    """
    root = Path(root).resolve()
    by_path: dict[str, AgentsMdSource] = {}
    for raw_path in changed_paths or ():
        relative_path = normalize_repo_relative_path(root, raw_path)
        target_dir = _path_directory(root, relative_path)
        for directory in ancestor_chain(str(root), str(target_dir)):
            directory_path = Path(directory)
            selected = next(
                (
                    directory_path / name
                    for name in candidate_names
                    if (directory_path / name).is_file()
                ),
                None,
            )
            if selected is None:
                continue
            source_path = selected.relative_to(root).as_posix()
            scope = directory_path.relative_to(root).as_posix() or "."
            source = by_path.setdefault(source_path, AgentsMdSource(source_path, scope))
            source.matched_paths.add(relative_path)
    return sorted(
        by_path.values(),
        key=lambda source: (source.scope.count("/"), source.path),
    )


discover_agents_md = collect_agents_md

__all__ = ["AgentsMdSource", "CANDIDATE_NAMES", "collect_agents_md", "discover_agents_md"]
