"""Adapter registry. Add a module here after writing its knowledge-skill spec,
fixtures and tests (see ../../AGENTS.md)."""

from __future__ import annotations

import importlib

from agent_logs.adapters.base import Adapter

# name -> "module:Class"
_REGISTRY = {
    "claude": "agent_logs.adapters.claude:ClaudeAdapter",
    "cursor": "agent_logs.adapters.cursor:CursorAdapter",
    "cline": "agent_logs.adapters.cline:ClineAdapter",
    "kilo": "agent_logs.adapters.kilo:KiloAdapter",
    "antigravity": "agent_logs.adapters.antigravity:AntigravityAdapter",
    "codex": "agent_logs.adapters.codex:CodexAdapter",
}

TOOL_NAMES = tuple(_REGISTRY)


def load(name: str) -> Adapter:
    module_name, cls_name = _REGISTRY[name].split(":")
    module = importlib.import_module(module_name)
    return getattr(module, cls_name)()


def load_many(names: list[str] | None) -> tuple[list[Adapter], list[str]]:
    """Instantiate adapters; a module that fails to import becomes a warning."""
    adapters: list[Adapter] = []
    errors: list[str] = []
    for name in names or TOOL_NAMES:
        try:
            adapters.append(load(name))
        except Exception as exc:  # noqa: BLE001 - isolate one broken adapter
            errors.append(f"{name}: adapter unavailable ({type(exc).__name__}: {exc})")
    return adapters, errors
