"""Compatibility exports for core and nested-agents-md discovery."""

from agent_tooling.core.discovery import ancestor_chain, find_repo_root
from agent_tooling.hooks.scenarios.nested_agents_md.discovery import (
    CANDIDATE_NAMES,
    DEFAULT_PATH_KEYS,
    collect_nested_agents_md,
    extract_generic_path_dirs,
    extract_path_dirs,
    path_to_touched_dir,
)

__all__ = [
    "CANDIDATE_NAMES",
    "DEFAULT_PATH_KEYS",
    "ancestor_chain",
    "collect_nested_agents_md",
    "extract_generic_path_dirs",
    "extract_path_dirs",
    "find_repo_root",
    "path_to_touched_dir",
]
