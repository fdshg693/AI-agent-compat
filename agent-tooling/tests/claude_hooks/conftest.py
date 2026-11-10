"""Fixtures for the Claude-only hooks (formerly .claude/hooks/tests/).

Unit tests import the adapter modules (``agent_tooling.adapters.claude.*``).
End-to-end tests copy the *generated* single-file hook into a throwaway
``<project>/.claude/hooks/`` and run it with stdin JSON, so install-location
path resolution (config/, .env, state/, logs/ next to the hook) is exercised
the same way it runs after ``skill-tools hooks install``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

GENERATED_CLAUDE = (
    Path(__file__).resolve().parents[2] / "agent_tooling" / "hooks" / "generated" / "claude"
)

# Env vars the hooks read; cleared so the developer's shell (or a Claude Code
# session running these tests) cannot leak into the results.
HOOK_ENV_VARS = (
    "CLAUDE_PROJECT_DIR",
    "HOOK_LOG",
    "NOTIFY_INJECTED_VARS",
    "SKILL_ENQUETE_MAX_ATTEMPTS",
    "LONG_RUN_OP_THRESHOLD",
    "LONG_RUN_FAILURE_STREAK_THRESHOLD",
    "STOP_ALERT_SOUND",
    "STOP_ALERT_SOUND_ENABLED",
    "STOP_ALERT_POPUP",
)


@dataclass
class InstalledHook:
    project: Path
    hooks_dir: Path
    script: Path
    home: Path

    @property
    def config_dir(self) -> Path:
        path = self.hooks_dir / "config"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run(
        self,
        payload: dict | str,
        *,
        env: dict[str, str] | None = None,
        project_env: bool = True,
        args: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        run_env = dict(os.environ)
        for key in HOOK_ENV_VARS:
            run_env.pop(key, None)
        run_env["HOME"] = str(self.home)
        run_env["USERPROFILE"] = str(self.home)
        if project_env:
            run_env["CLAUDE_PROJECT_DIR"] = str(self.project)
        if env:
            run_env.update(env)
        return subprocess.run(
            [sys.executable, str(self.script), *args],
            input=payload if isinstance(payload, str) else json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=run_env,
            timeout=30,
        )


@pytest.fixture
def install_hook(tmp_path):
    """Copy ``generated/claude/<hook_id>.py`` into ``<tmp>/project/.claude/hooks/``."""

    def install(hook_id: str) -> InstalledHook:
        source = GENERATED_CLAUDE / f"{hook_id}.py"
        assert source.is_file(), "run: just --justfile agent-tooling/justfile generate"
        project = tmp_path / "project"
        hooks_dir = project / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        script = hooks_dir / source.name
        shutil.copy(source, script)
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        return InstalledHook(project=project, hooks_dir=hooks_dir, script=script, home=home)

    return install


@pytest.fixture
def clean_hook_env(monkeypatch):
    for key in HOOK_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
