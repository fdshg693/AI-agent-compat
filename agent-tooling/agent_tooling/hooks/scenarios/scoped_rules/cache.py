"""Session cache for Rule bodies already emitted by scoped-rules."""

from __future__ import annotations

from agent_tooling.hooks.common.cache import load_cache, save_cache

from .definition import SCENARIO_ID

CACHE_NAME = "scoped-rules"


def cache_key(rule_path: str, content_fingerprint: str) -> str:
    return f"{SCENARIO_ID}\x00{rule_path}\x00{content_fingerprint}"


def load_emitted(session_id: str, cache_name: str = CACHE_NAME):
    return load_cache(session_id, cache_name)


def save_emitted(cache_path, emitted: set[str]) -> None:
    save_cache(cache_path, emitted)
