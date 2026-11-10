"""Tests for Claude Rule discovery and scoped-rules matching."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_tooling.hooks.scenarios.scoped_rules.discovery import (
    discover_scoped_rules,
    match_path,
    validate_rules,
)
from agent_tooling.hooks.scenarios.scoped_rules.rules import (
    RuleValidationError,
    parse_rule,
)
from agent_tooling.core.paths import normalize_repo_relative_path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    for rel, content in files.items():
        _write(repo / rel, content)
    return repo


def session(tmp_path: Path, label: str) -> str:
    digest = hashlib.sha1(str(tmp_path).encode("utf-8")).hexdigest()[:12]
    return f"{label}-{digest}"


def rule(*paths: str, body: str = "rule body\n") -> str:
    listed = "\n".join(f'  - "{path}"' for path in paths)
    return f"---\npaths:\n{listed}\n---\n{body}"


def test_parse_rule_reads_paths_and_fingerprints_body(tmp_path: Path):
    repo = make_repo(tmp_path, {".claude/rules/python.md": rule("**/*.py")})

    parsed = parse_rule(repo / ".claude/rules/python.md", repo)

    assert parsed.relative_path == ".claude/rules/python.md"
    assert parsed.paths == ("**/*.py",)
    assert parsed.body == "rule body"
    assert parsed.content_fingerprint == hashlib.sha256(b"rule body").hexdigest()


def test_normalize_repo_path_uses_posix_and_rejects_outside(tmp_path: Path):
    repo = make_repo(tmp_path, {})

    assert normalize_repo_relative_path(repo, "src\\app.py") == "src/app.py"
    with pytest.raises(ValueError, match="outside repository"):
        normalize_repo_relative_path(repo, "../outside.py")


def test_match_path_supports_project_wide_and_nested_globs():
    assert match_path("**", "README.md")
    assert match_path("**/*.py", "app.py")
    assert match_path("**/*.py", "src/app.py")
    assert match_path("src/**", "src/nested/app.py")
    assert not match_path("*.py", "src/app.py")


@pytest.mark.parametrize(
    "text",
    [
        "rule body without frontmatter\n",
        "---\ntitle: broken\n---\nbody\n",
        "---\npaths: hooks/**\n---\nbody\n",
        "---\npaths:\n  - 42\n---\nbody\n",
    ],
)
def test_parse_rule_rejects_invalid_frontmatter(tmp_path: Path, text: str):
    repo = make_repo(tmp_path, {".claude/rules/broken.md": text})

    with pytest.raises(RuleValidationError):
        parse_rule(repo / ".claude/rules/broken.md", repo)


def test_discovery_matches_touched_paths_without_expanding_globs(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {
            ".claude/rules/python.md": rule("**/*.py", "src/**"),
            ".claude/rules/docs.md": rule("docs/**"),
            "src/app.py": "pass\n",
            "docs/readme.md": "docs\n",
        },
    )

    found = discover_scoped_rules(
        repo,
        ["src\\app.py", "docs/readme.md", "new/file.py"],
        session_id=session(tmp_path, "rules-match"),
    )

    assert [item.rule_path for item in found] == [
        ".claude/rules/docs.md",
        ".claude/rules/python.md",
    ]
    python = found[1]
    assert python.file_path == "new/file.py"
    assert {origin.pattern for origin in python.origins} == {"**/*.py", "src/**"}
    assert {origin.matched_path for origin in python.origins} == {"new/file.py", "src/app.py"}


def test_discovery_returns_no_candidates_for_unmatched_paths(tmp_path: Path):
    repo = make_repo(tmp_path, {".claude/rules/python.md": rule("**/*.py")})

    assert (
        discover_scoped_rules(
            repo,
            ["docs/readme.md"],
            session_id=session(tmp_path, "rules-empty"),
        )
        == []
    )


def test_regex_filter_uses_fullmatch_and_all_patterns(tmp_path: Path):
    repo = make_repo(tmp_path, {".claude/rules/all.md": rule("**")})

    found = discover_scoped_rules(
        repo,
        ["src/app.py", "src/app.py.bak"],
        session_id=session(tmp_path, "rules-regex"),
        file_regexes=(r"src/.*", r".*\.py"),
    )

    assert found[0].file_path == "src/app.py"
    assert {origin.matched_path for origin in found[0].origins} == {"src/app.py"}

    with pytest.raises(RuleValidationError, match="invalid regex"):
        discover_scoped_rules(
            repo,
            ["src/app.py"],
            session_id=session(tmp_path, "rules-invalid-regex"),
            file_regexes=("[",),
        )

    with pytest.raises(RuleValidationError, match="entries must be strings"):
        discover_scoped_rules(
            repo,
            ["src/app.py"],
            session_id=session(tmp_path, "rules-invalid-regex-type"),
            file_regexes=(42,),  # type: ignore[arg-type]
        )


def test_rule_cache_is_keyed_by_content_fingerprint(tmp_path: Path):
    rule_path = ".claude/rules/python.md"
    repo = make_repo(tmp_path, {rule_path: rule("**/*.py", body="first\n")})
    session_id = session(tmp_path, "rules-cache")

    first = discover_scoped_rules(repo, ["src/app.py"], session_id=session_id)
    second = discover_scoped_rules(repo, ["src/app.py"], session_id=session_id)
    assert len(first) == 1
    assert second == []

    _write(repo / rule_path, rule("**/*.py", body="changed\n"))
    third = discover_scoped_rules(repo, ["src/app.py"], session_id=session_id)
    assert len(third) == 1
    assert third[0].body == "changed"


def test_validate_rules_reports_all_invalid_rule_files(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {
            ".claude/rules/good.md": rule("src/**"),
            ".claude/rules/bad.md": "---\npaths: nope\n---\nbody\n",
        },
    )

    with pytest.raises(RuleValidationError, match="bad.md"):
        validate_rules(repo)
