"""Shared AGENTS.md discovery (source modules)."""

from __future__ import annotations

import os
from pathlib import Path

from agent_tooling.core.bash import extract_bash_dirs
from agent_tooling.hooks.common.cache import load_cache
from agent_tooling.core.discovery import ancestor_chain, find_repo_root
from agent_tooling.hooks.common.discovery import (
    collect_nested_agents_md,
    extract_generic_path_dirs,
)
from agent_tooling.core.paths import split_subcommands, tokenize


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


def test_find_repo_root_walks_to_git(tmp_path: Path):
    repo = make_repo(tmp_path, {"pkg/nested/file.txt": "x"})
    assert find_repo_root(str(repo / "pkg" / "nested")) == str(repo.resolve())


def test_ancestor_chain_inside_and_outside(tmp_path: Path):
    repo = make_repo(tmp_path, {"pkg/file.txt": "x"})
    root = str(repo)
    pkg = str(repo / "pkg")
    chain = ancestor_chain(root, pkg)
    assert [os.path.normcase(os.path.normpath(p)) for p in chain] == [
        os.path.normcase(os.path.normpath(root)),
        os.path.normcase(os.path.normpath(pkg)),
    ]
    assert ancestor_chain(root, str(tmp_path / "elsewhere")) == []


def test_tokenize_and_split_subcommands():
    assert tokenize("cat 'foo bar.txt'") == ["cat", "foo bar.txt"]
    parts = split_subcommands("cd pkg && cat AGENTS.md")
    assert parts == ["cd pkg", "cat AGENTS.md"]


def test_extract_bash_dirs_cat_and_cd_chain(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {
            "pkg/AGENTS.md": "nested",
            "pkg/file.py": "print(1)\n",
        },
    )
    cwd = str(repo)
    dirs = extract_bash_dirs("cd pkg && cat file.py", cwd)
    assert os.path.normcase(os.path.normpath(str(repo / "pkg"))) in {
        os.path.normcase(os.path.normpath(d)) for d in dirs
    }


def test_extract_bash_dirs_rg_skips_pattern(tmp_path: Path):
    repo = make_repo(tmp_path, {"pkg/file.py": "x"})
    dirs = extract_bash_dirs("rg nested-pattern pkg/file.py", str(repo))
    assert os.path.normcase(os.path.normpath(str(repo / "pkg"))) in {
        os.path.normcase(os.path.normpath(d)) for d in dirs
    }


def test_extract_bash_dirs_ignores_missing_paths(tmp_path: Path):
    repo = make_repo(tmp_path, {"pkg/file.py": "x"})
    assert extract_bash_dirs("cat no-such-file.txt", str(repo)) == set()


def test_extract_generic_path_dirs_uses_dirname(tmp_path: Path):
    repo = make_repo(tmp_path, {"pkg/file.py": "x"})
    dirs = extract_generic_path_dirs({"file_path": "pkg/file.py"}, str(repo))
    assert os.path.normcase(os.path.normpath(str(repo / "pkg"))) in {
        os.path.normcase(os.path.normpath(d)) for d in dirs
    }


def test_collect_prefers_override_and_skips_covered(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {
            "AGENTS.md": "root-agents",
            "pkg/AGENTS.md": "pkg-agents",
            "pkg/AGENTS.override.md": "pkg-override",
            "pkg/file.py": "x",
        },
    )
    root = str(repo)
    found = collect_nested_agents_md(
        root,
        {str(repo / "pkg")},
        ancestor_chain(root, root),
        session_id="sess-override",
        cache_name="nested-agents-md-test-override",
    )
    assert found == [("pkg/AGENTS.override.md", "pkg-override")]


def test_collect_records_cache_even_without_file(tmp_path: Path):
    repo = make_repo(tmp_path, {"pkg/file.py": "x"})
    root = str(repo)
    cache_name = "nested-agents-md-test-empty"
    session_id = "sess-empty"
    first = collect_nested_agents_md(
        root,
        {str(repo / "pkg")},
        ancestor_chain(root, root),
        session_id=session_id,
        cache_name=cache_name,
    )
    assert first == []
    _path, seen = load_cache(session_id, cache_name)
    assert os.path.normcase(os.path.normpath(str(repo / "pkg"))) in {
        os.path.normcase(os.path.normpath(p)) for p in seen
    }
    _write(repo / "pkg" / "AGENTS.md", "late")
    second = collect_nested_agents_md(
        root,
        {str(repo / "pkg")},
        ancestor_chain(root, root),
        session_id=session_id,
        cache_name=cache_name,
    )
    assert second == []


def test_collect_empty_touched_dirs_does_not_write_cache(tmp_path: Path):
    repo = make_repo(tmp_path, {"AGENTS.md": "root"})
    found = collect_nested_agents_md(
        str(repo),
        set(),
        set(),
        session_id="sess-none",
        cache_name="nested-agents-md-test-none",
    )
    assert found == []
    cache_path, seen = load_cache("sess-none", "nested-agents-md-test-none")
    assert seen == set()
    assert not os.path.exists(cache_path)
