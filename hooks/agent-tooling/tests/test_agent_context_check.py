"""Tests for staged agent-context coverage reporting."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import agent_tooling.checks.agent_context as agent_context
from agent_tooling.checks.agent_context import (
    StagedChange,
    _parse_name_status_z,
    build_context_report,
    staged_changes,
)
from agent_tooling.cli import main
from agent_tooling.hooks.common.rules import RuleValidationError


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rule(*patterns: str, body: str = "rule body\n") -> str:
    listed = "\n".join(f'  - "{pattern}"' for pattern in patterns)
    if patterns:
        frontmatter = f"paths:\n{listed}"
    else:
        frontmatter = "description: always"
    return f"---\n{frontmatter}\n---\n{body}"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def make_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test")
    return repo


def test_name_status_parser_preserves_rename_and_special_paths():
    parsed = _parse_name_status_z(
        b"A\0space name.py\0R100\0old\tname.py\0new\nname.py\0D\0deleted.py\0"
    )
    assert [(change.status, change.path, change.old_path) for change in parsed] == [
        ("D", "deleted.py", None),
        ("R100", "new\nname.py", "old\tname.py"),
        ("A", "space name.py", None),
    ]


def test_sources_are_deduplicated_and_rules_group_patterns(tmp_path: Path):
    repo = make_git_repo(tmp_path)
    write(repo / "AGENTS.md", "root")
    write(repo / "pkg" / "AGENTS.md", "pkg")
    write(repo / "pkg" / "app.py", "pass")
    write(repo / ".claude/rules/python.md", rule("**/*.py", "pkg/**"))
    write(repo / ".claude/rules/always.md", rule())

    report = build_context_report(
        repo,
        [
            # The rename record contributes both old and new paths.
            # A regular change is enough to exercise source aggregation here.
            StagedChange("R100", "pkg/app.py", "old.py"),
        ],
    )
    data = report.as_dict()
    assert data["changed_paths"] == ["old.py", "pkg/app.py"]
    assert [source["path"] for source in data["sources"]] == [
        "AGENTS.md",
        "pkg/AGENTS.md",
        ".claude/rules/always.md",
        ".claude/rules/python.md",
    ]
    python = data["sources"][-1]
    assert {origin["pattern"] for origin in python["origins"]} == {"**/*.py", "pkg/**"}
    matched = {origin["pattern"]: origin["matched_paths"] for origin in python["origins"]}
    assert matched["**/*.py"] == ["old.py", "pkg/app.py"]
    assert matched["pkg/**"] == ["pkg/app.py"]


def test_always_rule_is_reported_once_and_rule_file_is_candidate(tmp_path: Path):
    repo = make_git_repo(tmp_path)
    write(repo / ".claude/rules/always.md", rule())
    report = build_context_report(repo, [StagedChange("A", ".claude/rules/always.md")])
    source = report.as_dict()["sources"][0]
    assert source["scope"] == "always"
    assert source["origins"][0]["pattern"] == "<always>"
    assert source["origins"][0]["matched_paths"] == [".claude/rules/always.md"]


def test_malformed_rule_is_not_silently_omitted(tmp_path: Path):
    repo = make_git_repo(tmp_path)
    write(repo / ".claude/rules/broken.md", "---\npaths: []\n---\nbroken")
    with pytest.raises(RuleValidationError, match="broken.md"):
        build_context_report(
            repo,
            [StagedChange("A", "src/app.py")],
        )


def test_staged_changes_reads_only_index(tmp_path: Path):
    repo = make_git_repo(tmp_path)
    write(repo / "staged.py", "staged")
    write(repo / "unstaged.py", "unstaged")
    git(repo, "add", "staged.py")
    changes = staged_changes(repo)
    assert [(change.status, change.path) for change in changes] == [("A", "staged.py")]


def test_cli_text_and_json_have_same_sources(tmp_path: Path, capsys, monkeypatch):
    repo = make_git_repo(tmp_path)
    write(repo / "AGENTS.md", "root")
    write(repo / "src" / "app.py", "pass")
    git(repo, "add", ".")

    monkeypatch.chdir(repo)
    assert main(["--staged"]) == 0
    text = capsys.readouterr().out
    assert "AGENTS.md" in text
    assert main(["--staged", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["changed_paths"] == ["AGENTS.md", "src/app.py"]
    assert payload["sources"][0]["path"] == "AGENTS.md"
    assert "Context sources:" in text


def test_cli_rejects_non_repository(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["--staged"]) != 0
    assert "Git repository" in capsys.readouterr().err


def test_explain_accepts_unstaged_relative_absolute_and_missing_files(tmp_path: Path):
    repo = make_git_repo(tmp_path)
    write(repo / "AGENTS.md", "root")
    write(repo / "pkg" / "AGENTS.override.md", "pkg")
    write(repo / ".claude/rules/python.md", rule("pkg/**/*.py"))
    target = repo / "pkg" / "src" / "new.py"

    relative = agent_context.explain_context(repo, "pkg/src/new.py")
    absolute = agent_context.explain_context(repo, target)

    assert relative == absolute
    data = relative.as_dict()
    assert data["target"] == "pkg/src/new.py"
    assert [source["path"] for source in data["sources"]] == [
        "AGENTS.md",
        "pkg/AGENTS.override.md",
        ".claude/rules/python.md",
    ]
    assert data["sources"][0]["reason"] == "ancestor scope: ."
    assert data["sources"][1]["reason"] == "ancestor scope: pkg"
    assert data["sources"][2]["reason"] == "matches path pattern: pkg/**/*.py"


def test_explain_rejects_outside_directory_and_symlink_targets(tmp_path: Path):
    repo = make_git_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    write(outside / "secret.py", "secret")

    with pytest.raises(ValueError, match="outside repository"):
        agent_context.explain_context(repo, outside / "secret.py")
    with pytest.raises(ValueError, match="directory"):
        agent_context.explain_context(repo, repo)

    link = repo / "linked.py"
    try:
        link.symlink_to(outside / "secret.py")
    except OSError as exc:
        pytest.skip(f"symlinks are not available: {exc}")
    with pytest.raises(ValueError, match="outside repository"):
        agent_context.explain_context(repo, link)


def test_explain_rejects_symlinked_external_rule_sources_before_reading(tmp_path: Path):
    repo = make_git_repo(tmp_path)
    outside = tmp_path / "outside.md"
    write(outside, rule("**/*.py"))
    rules = repo / ".claude" / "rules"
    rules.mkdir(parents=True)
    link = rules / "external.md"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are not available: {exc}")

    with pytest.raises(ValueError, match="outside repository"):
        agent_context.explain_context(repo, "src/app.py")


def test_explain_rejects_symlinked_external_agents_source(tmp_path: Path):
    repo = make_git_repo(tmp_path)
    outside = tmp_path / "outside.md"
    write(outside, "external guidance")
    link = repo / "AGENTS.md"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are not available: {exc}")

    with pytest.raises(ValueError, match="outside repository"):
        agent_context.explain_context(repo, "src/app.py")


def test_explain_cli_text_json_and_staged_check_contract(tmp_path: Path, capsys, monkeypatch):
    repo = make_git_repo(tmp_path)
    write(repo / "AGENTS.md", "root")
    write(repo / "src" / "app.py", "pass")
    monkeypatch.chdir(repo)

    assert main(["explain", "src/app.py"]) == 0
    text = capsys.readouterr().out
    assert "Target: src/app.py" in text
    assert "ancestor scope: ." in text
    assert "candidate list" in text

    assert main(["explain", "src/app.py", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["target"] == "src/app.py"
    assert payload["sources"][0]["reason"] == "ancestor scope: ."

    write(repo / "staged.py", "staged")
    git(repo, "add", "staged.py")
    assert main(["--staged", "--format", "json"]) == 0
    staged_payload = json.loads(capsys.readouterr().out)
    assert set(staged_payload) == {"changed_paths", "changes", "sources"}
    assert staged_payload["changed_paths"] == ["staged.py"]


def test_explain_cli_reports_external_cwd_and_malformed_rules(tmp_path: Path, capsys, monkeypatch):
    nested = tmp_path / "nested"
    nested.mkdir()
    repo = make_git_repo(nested)
    outside = tmp_path / "external-cwd"
    outside.mkdir()
    monkeypatch.chdir(outside)
    assert main(["explain", "new.py"]) != 0
    assert "cannot find Git repository" in capsys.readouterr().err

    write(repo / ".claude/rules/broken.md", "---\npaths: []\n---\nbroken")
    nested = repo / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    assert main(["explain", "../src/app.py"]) != 0
    assert "broken.md" in capsys.readouterr().err


def test_cli_version_is_standalone(capsys, monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out == "agent-context-check 0.1.0\n"
