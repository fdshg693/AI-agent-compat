"""Compatibility exports for the core touched-path helpers."""

from agent_tooling.core.scoped import (
    extract_patch_paths,
    normalize_touched_paths,
    render_rule_context,
)

__all__ = ["extract_patch_paths", "normalize_touched_paths", "render_rule_context"]
