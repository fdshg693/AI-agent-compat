"""recommend_skills (UserPromptSubmit): skill collection/parsing units and no-op e2e paths.

Paths that reach ``aim_cli`` need network and an API key, so e2e covers only
the fall-through cases. The generated hook keeps ``import yaml`` (declared in
``project_imports``); the test venv has PyYAML via the dev group.
"""

from __future__ import annotations

from agent_tooling.adapters.claude import recommend_skills as hook


def _write_skill(dir_path, name=None, description="does something useful", extra=""):
    dir_path.mkdir(parents=True, exist_ok=True)
    frontmatter = "---\n"
    if name is not None:
        frontmatter += f"name: {name}\n"
    frontmatter += f"description: {description}\n"
    frontmatter += extra
    frontmatter += "---\n\nBody text.\n"
    (dir_path / "SKILL.md").write_text(frontmatter, encoding="utf-8")


# ---------------------------------------------------------------------------
# read_skill
# ---------------------------------------------------------------------------


def test_read_skill_valid_frontmatter(tmp_path):
    skill_dir = tmp_path / "my-skill"
    _write_skill(skill_dir, name="my-skill", description="Use this for X.")
    entry = hook.read_skill(skill_dir / "SKILL.md")
    assert entry["name"] == "my-skill"
    assert entry["description"] == "Use this for X."
    assert entry["path"] == (skill_dir / "SKILL.md").as_posix()


def test_read_skill_missing_description_returns_none(tmp_path):
    skill_dir = tmp_path / "no-desc"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: no-desc\n---\nbody\n", encoding="utf-8")
    assert hook.read_skill(skill_dir / "SKILL.md") is None


def test_read_skill_name_falls_back_to_parent_dir(tmp_path):
    skill_dir = tmp_path / "folder-name"
    _write_skill(skill_dir, name=None, description="Some description.")
    assert hook.read_skill(skill_dir / "SKILL.md")["name"] == "folder-name"


def test_read_skill_invalid_yaml_returns_none(tmp_path):
    skill_dir = tmp_path / "bad-yaml"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: [unterminated\n---\nbody\n", encoding="utf-8")
    assert hook.read_skill(skill_dir / "SKILL.md") is None


def test_read_skill_no_frontmatter_returns_none(tmp_path):
    skill_dir = tmp_path / "plain"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("just a plain markdown file\n", encoding="utf-8")
    assert hook.read_skill(skill_dir / "SKILL.md") is None


# ---------------------------------------------------------------------------
# collect_skills
# ---------------------------------------------------------------------------


def test_collect_skills_dedup_by_name_first_root_wins(tmp_path):
    _write_skill(tmp_path / "roots_a" / "dup", name="dup", description="from A")
    _write_skill(tmp_path / "roots_b" / "dup", name="dup", description="from B")
    warnings = []
    skills = hook.collect_skills(
        tmp_path, ["roots_a", "roots_b"], max_skills=100, warnings=warnings
    )
    assert len(skills) == 1
    assert skills[0]["description"] == "from A"
    assert warnings == []


def test_collect_skills_ignores_missing_root(tmp_path):
    warnings = []
    assert (
        hook.collect_skills(tmp_path, ["does-not-exist"], max_skills=100, warnings=warnings) == []
    )
    assert warnings == []


def test_collect_skills_respects_max_skills_cap(tmp_path):
    for i in range(5):
        _write_skill(tmp_path / "roots" / f"skill-{i}", name=f"skill-{i}", description="d")
    warnings = []
    skills = hook.collect_skills(tmp_path, ["roots"], max_skills=2, warnings=warnings)
    assert len(skills) == 2
    assert any("capped" in w for w in warnings)


def test_collect_skills_recurses_nested_plugin_layout(tmp_path):
    root = tmp_path / "skills/plugins"
    _write_skill(root / "pluginA" / "skills" / "foo", name="foo", description="foo desc")
    _write_skill(root / "pluginB" / "skills" / "bar", name="bar", description="bar desc")
    skills = hook.collect_skills(tmp_path, ["skills/plugins"], max_skills=100, warnings=[])
    assert {s["name"] for s in skills} == {"foo", "bar"}


# ---------------------------------------------------------------------------
# make_batches / parse_recommendations
# ---------------------------------------------------------------------------


def test_make_batches_splits_by_size_and_sorts_by_name():
    skills = [{"name": n, "description": "d"} for n in ["c", "a", "b", "d", "e"]]
    batches = hook.make_batches(skills, batch_size=2)
    assert [[s["name"] for s in b] for b in batches] == [["a", "b"], ["c", "d"], ["e"]]


def test_make_batches_empty_input():
    assert hook.make_batches([], batch_size=30) == []


def _batch(*names):
    return [{"name": n, "description": f"{n} desc", "path": f"/skills/{n}/SKILL.md"} for n in names]


def test_parse_recommendations_exact_match():
    results = hook.parse_recommendations(
        "alpha :: helps with alpha tasks\n", _batch("alpha", "beta")
    )
    assert [(r["name"], r["reason"]) for r in results] == [("alpha", "helps with alpha tasks")]


def test_parse_recommendations_case_insensitive_match():
    results = hook.parse_recommendations("alpha-skill :: matches\n", _batch("Alpha-Skill"))
    assert [r["name"] for r in results] == ["Alpha-Skill"]


def test_parse_recommendations_ignores_hallucinated_name():
    assert hook.parse_recommendations("made-up-skill :: not real\n", _batch("alpha")) == []


def test_parse_recommendations_ignores_lines_without_delimiter():
    assert hook.parse_recommendations("just some prose\n", _batch("alpha")) == []


def test_parse_recommendations_dedupes_repeated_name():
    results = hook.parse_recommendations("alpha :: first\nalpha :: second\n", _batch("alpha"))
    assert [r["reason"] for r in results] == ["first"]


def test_parse_recommendations_strips_bullet_prefix():
    assert len(hook.parse_recommendations("- alpha :: bulleted\n", _batch("alpha"))) == 1


def test_parse_recommendations_no_reason_falls_back_to_placeholder():
    results = hook.parse_recommendations("alpha ::   \n", _batch("alpha"))
    assert results[0]["reason"] == "(no reason given)"


def test_parse_recommendations_empty_response():
    assert hook.parse_recommendations("", _batch("alpha")) == []


# ---------------------------------------------------------------------------
# End-to-end (no-op paths only)
# ---------------------------------------------------------------------------


def _assert_noop(result):
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_e2e_wrong_event_is_noop(install_hook):
    _assert_noop(install_hook("recommend_skills").run({"hook_event_name": "Stop"}))


def test_e2e_empty_prompt_is_noop(install_hook):
    hook_ = install_hook("recommend_skills")
    _assert_noop(hook_.run({"hook_event_name": "UserPromptSubmit", "prompt": "   "}))


def test_e2e_unparsable_stdin_is_noop(install_hook):
    _assert_noop(install_hook("recommend_skills").run("not json"))


def test_e2e_missing_config_is_noop(install_hook):
    hook_ = install_hook("recommend_skills")
    _assert_noop(hook_.run({"hook_event_name": "UserPromptSubmit", "prompt": "do something"}))


def test_e2e_no_roots_configured_is_noop(install_hook):
    hook_ = install_hook("recommend_skills")
    (hook_.config_dir / "recommend_skills.yaml").write_text("roots: []\n", encoding="utf-8")
    _assert_noop(hook_.run({"hook_event_name": "UserPromptSubmit", "prompt": "do something"}))


def test_e2e_roots_with_no_skill_md_is_noop(install_hook):
    hook_ = install_hook("recommend_skills")
    (hook_.project / "empty-root").mkdir()
    (hook_.config_dir / "recommend_skills.yaml").write_text(
        "roots:\n  - empty-root\n", encoding="utf-8"
    )
    _assert_noop(hook_.run({"hook_event_name": "UserPromptSubmit", "prompt": "do something"}))
