"""Codex complete exploration matches the live .codex/hooks script."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from agent_tooling.adapters.codex.nested_agents_md import extract_touched_dirs
from agent_tooling.core.bash import extract_bash_dirs
from agent_tooling.core.discovery import ancestor_chain, find_repo_root
from agent_tooling.core.paths import split_subcommands, tokenize

REPO_ROOT = Path(__file__).resolve().parents[2]
NESTED = (
    REPO_ROOT
    / "agent-tooling"
    / "agent_tooling"
    / "hooks"
    / "generated"
    / "codex"
    / "nested_agents_md.py"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def test_nested_helpers_match_generated_target(tmp_path: Path):
    generated = _load("generated_codex_hook", NESTED)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "file.py").write_text("print(1)\n", encoding="utf-8")
    (pkg / "AGENTS.md").write_text("nested-agents", encoding="utf-8")
    (pkg / "other.txt").write_text("x\n", encoding="utf-8")

    cwd = str(repo)
    command = 'cd pkg && cat "file.py"'
    assert tokenize(command) == generated.tokenize(command)
    assert split_subcommands(command) == generated.split_subcommands(command)

    src_dirs = extract_bash_dirs(command, cwd)
    assert {_norm(d) for d in src_dirs} == {
        _norm(d) for d in generated.extract_bash_dirs(command, cwd)
    }

    root = find_repo_root(str(pkg))
    assert root == generated.find_repo_root(str(pkg))
    chain = ancestor_chain(root, str(pkg))
    assert [_norm(p) for p in chain] == [_norm(p) for p in generated.ancestor_chain(root, str(pkg))]

    patch_input = {"command": "*** Update File: pkg/file.py\n@@\n-print(1)\n+print(2)\n"}
    src_patch = extract_touched_dirs("apply_patch", patch_input, cwd)
    generated_patch = generated.extract_touched_dirs("apply_patch", patch_input, cwd)
    assert {_norm(d) for d in src_patch} == {_norm(d) for d in generated_patch}


def _run_hook(script: Path, payload: dict) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout


def test_generated_stdin_finds_nested_file(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "file.py").write_text("x\n", encoding="utf-8")
    (pkg / "AGENTS.md").write_text("from-pkg", encoding="utf-8")

    payload = {
        "cwd": str(repo),
        "session_id": "parity-nested-1",
        "tool_name": "Bash",
        "tool_input": {"command": "cat pkg/file.py"},
    }
    code, stdout = _run_hook(NESTED, payload)
    assert code == 0
    context = json.loads(stdout)["hookSpecificOutput"]["additionalContext"]
    assert "pkg/AGENTS.md:" in context
    assert "from-pkg" in context
