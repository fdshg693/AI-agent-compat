"""skill_usage_tracker (PostToolUse) + skill_enquete_stop (Stop): the auto-enquete pair.

Both hooks share ``state/skill_usage/<session_id>.json`` next to the installed
hooks, so the e2e tests install them into the same ``.claude/hooks/``.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_tooling.adapters.claude import skill_enquete_stop as stop_hook
from agent_tooling.adapters.claude import skill_usage_tracker as tracker
from agent_tooling.adapters.claude.common.skill_enquete_state import (
    load_state,
    save_state,
    state_path,
)
from agent_tooling.adapters.claude.common.skill_frontmatter import (
    find_skill_dir_by_name,
    read_frontmatter,
)


def _write_skill(dir_path, name=None, auto_enquete=None, description="does X"):
    dir_path.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    if name is not None:
        lines.append(f"name: {name}")
    lines.append(f"description: {description}")
    if auto_enquete is not None:
        lines.append(f"auto-enquete: {'true' if auto_enquete else 'false'}")
    lines += ["---", "", "Body text."]
    (dir_path / "SKILL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# common/skill_frontmatter.py
# ---------------------------------------------------------------------------


def test_read_frontmatter_valid(tmp_path):
    _write_skill(tmp_path, name="foo", auto_enquete=True)
    data = read_frontmatter(tmp_path / "SKILL.md")
    assert data["name"] == "foo"
    assert data["auto-enquete"] is True


def test_read_frontmatter_no_frontmatter_returns_none(tmp_path):
    (tmp_path / "SKILL.md").write_text("just body, no frontmatter\n", encoding="utf-8")
    assert read_frontmatter(tmp_path / "SKILL.md") is None


def test_read_frontmatter_invalid_yaml_returns_none(tmp_path):
    (tmp_path / "SKILL.md").write_text("---\nname: [unterminated\n---\nbody\n", encoding="utf-8")
    assert read_frontmatter(tmp_path / "SKILL.md") is None


def test_read_frontmatter_missing_file_returns_none(tmp_path):
    assert read_frontmatter(tmp_path / "does-not-exist.md") is None


def test_find_skill_dir_by_frontmatter_name(tmp_path):
    skill_dir = tmp_path / "on-disk-dirname"
    _write_skill(skill_dir, name="real-name", auto_enquete=True)
    assert find_skill_dir_by_name("real-name", [tmp_path]) == skill_dir


def test_find_skill_dir_falls_back_to_dirname(tmp_path):
    skill_dir = tmp_path / "my-skill"
    _write_skill(skill_dir, name=None)
    assert find_skill_dir_by_name("my-skill", [tmp_path]) == skill_dir


def test_find_skill_dir_name_match_wins_over_dirname_fallback(tmp_path):
    _write_skill(tmp_path / "target-name", name="not-target-name")
    real_dir = tmp_path / "other-dirname"
    _write_skill(real_dir, name="target-name")
    assert find_skill_dir_by_name("target-name", [tmp_path]) == real_dir


def test_find_skill_dir_no_match_returns_none(tmp_path):
    _write_skill(tmp_path / "unrelated", name="unrelated")
    assert find_skill_dir_by_name("nope", [tmp_path]) is None


def test_find_skill_dir_missing_root_is_skipped(tmp_path):
    assert find_skill_dir_by_name("anything", [tmp_path / "does-not-exist"]) is None


# ---------------------------------------------------------------------------
# skill_usage_tracker units
# ---------------------------------------------------------------------------


def test_resolve_skill_md_for_read_matches_skill_md(tmp_path):
    _write_skill(tmp_path, name="foo")
    resolved = tracker.resolve_skill_md_for_read(str(tmp_path / "SKILL.md"))
    assert resolved == (tmp_path / "SKILL.md").resolve()


def test_resolve_skill_md_for_read_rejects_other_filenames(tmp_path):
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    assert tracker.resolve_skill_md_for_read(str(tmp_path / "README.md")) is None


def test_resolve_skill_md_for_read_missing_file_returns_none(tmp_path):
    assert tracker.resolve_skill_md_for_read(str(tmp_path / "SKILL.md")) is None


def test_load_roots_reads_config_and_appends_home_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    config = tmp_path / "skill_usage_tracker.yaml"
    config.write_text("roots:\n  - .claude/skills\n", encoding="utf-8")
    roots = tracker.load_roots(tmp_path, config)
    assert (tmp_path / ".claude" / "skills") in roots
    assert roots[-1] == Path.home() / ".claude" / "skills"


def test_load_roots_no_config_defaults_to_home_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    roots = tracker.load_roots(tmp_path, tmp_path / "missing.yaml")
    assert roots == [Path.home() / ".claude" / "skills"]


# ---------------------------------------------------------------------------
# skill_enquete_stop units
# ---------------------------------------------------------------------------


def test_build_template_contains_all_questions_and_no_placeholder_gaps():
    template = stop_hook.build_template("my-skill", "sess-1")
    assert "skill: my-skill" in template
    assert "session_id: sess-1" in template
    for q in stop_hook.QUESTIONS:
        assert q in template
    assert template.count("(ここに回答)") == len(stop_hook.QUESTIONS)


def test_build_message_lists_each_pending_skill_and_its_target():
    pending = [
        {"name": "skill-a", "target": "/abs/path/skill-a/enquete/sess-1.md"},
        {"name": "skill-b", "target": "/abs/path/skill-b/enquete/sess-1.md"},
    ]
    message = stop_hook.build_message(pending, "sess-1")
    for item in pending:
        assert item["name"] in message
        assert item["target"] in message


# ---------------------------------------------------------------------------
# End-to-end: skill_usage_tracker
# ---------------------------------------------------------------------------


def _read_payload(path, session_id="sess-1"):
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Read"}
    payload["tool_input"] = {"file_path": str(path)}
    if session_id:
        payload["session_id"] = session_id
    return payload


def _skill_payload(skill, session_id):
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Skill",
        "tool_input": {"skill": skill},
        "session_id": session_id,
    }


def test_e2e_read_skill_md_with_auto_enquete_records(install_hook):
    hook_ = install_hook("skill_usage_tracker")
    skill_dir = hook_.project / ".claude" / "skills" / "target-skill"
    _write_skill(skill_dir, name="target-skill", auto_enquete=True)

    result = hook_.run(_read_payload(skill_dir / "SKILL.md"))
    assert result.returncode == 0, result.stderr
    state = load_state(state_path(hook_.hooks_dir, "sess-1"))
    assert state["skills"]["target-skill"]["dir"] == skill_dir.resolve().as_posix()


def test_e2e_read_skill_md_without_auto_enquete_is_noop(install_hook):
    hook_ = install_hook("skill_usage_tracker")
    skill_dir = hook_.project / ".claude" / "skills" / "plain-skill"
    _write_skill(skill_dir, name="plain-skill", auto_enquete=False)
    assert hook_.run(_read_payload(skill_dir / "SKILL.md", "sess-2")).returncode == 0
    assert not state_path(hook_.hooks_dir, "sess-2").exists()


def test_e2e_read_non_skill_md_is_noop(install_hook):
    hook_ = install_hook("skill_usage_tracker")
    other = hook_.project / "README.md"
    other.write_text("hello", encoding="utf-8")
    assert hook_.run(_read_payload(other, "sess-3")).returncode == 0
    assert not state_path(hook_.hooks_dir, "sess-3").exists()


def _write_roots_config(hook_, roots):
    body = "roots:\n" + "".join(f"  - {r}\n" for r in roots)
    (hook_.config_dir / "skill_usage_tracker.yaml").write_text(body, encoding="utf-8")


def test_e2e_skill_tool_invocation_resolves_name_and_records(install_hook):
    hook_ = install_hook("skill_usage_tracker")
    skill_dir = hook_.project / "skills/plugins" / "cc-knowledge" / "skills" / "on-disk-name"
    _write_skill(skill_dir, name="my-skill", auto_enquete=True)
    _write_roots_config(hook_, ["skills/plugins/cc-knowledge/skills"])

    assert hook_.run(_skill_payload("my-skill", "sess-4")).returncode == 0
    assert "my-skill" in load_state(state_path(hook_.hooks_dir, "sess-4"))["skills"]


def test_e2e_skill_tool_invocation_with_plugin_prefix(install_hook):
    hook_ = install_hook("skill_usage_tracker")
    skill_dir = hook_.project / "skills/plugins" / "cc-knowledge" / "skills" / "prefixed-skill"
    _write_skill(skill_dir, name="prefixed-skill", auto_enquete=True)
    _write_roots_config(hook_, ["skills/plugins/cc-knowledge/skills"])

    assert hook_.run(_skill_payload("myplugin:prefixed-skill", "sess-5")).returncode == 0
    assert "prefixed-skill" in load_state(state_path(hook_.hooks_dir, "sess-5"))["skills"]


def test_e2e_skill_roots_resolve_from_payload_cwd_without_project_env(install_hook):
    hook_ = install_hook("skill_usage_tracker")
    skill_dir = hook_.project / "skills" / "cwd-skill"
    _write_skill(skill_dir, name="cwd-skill", auto_enquete=True)
    _write_roots_config(hook_, ["skills"])

    payload = {**_skill_payload("cwd-skill", "sess-7"), "cwd": str(hook_.project)}
    assert hook_.run(payload, project_env=False).returncode == 0
    assert "cwd-skill" in load_state(state_path(hook_.hooks_dir, "sess-7"))["skills"]


def test_e2e_missing_session_id_is_noop(install_hook):
    hook_ = install_hook("skill_usage_tracker")
    skill_dir = hook_.project / ".claude" / "skills" / "target-skill"
    _write_skill(skill_dir, name="target-skill", auto_enquete=True)
    assert hook_.run(_read_payload(skill_dir / "SKILL.md", session_id=None)).returncode == 0
    assert not (hook_.hooks_dir / "state").exists()


def test_e2e_other_tool_is_noop(install_hook):
    hook_ = install_hook("skill_usage_tracker")
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": "sess-6"}
    assert hook_.run(payload).returncode == 0
    assert not state_path(hook_.hooks_dir, "sess-6").exists()


# ---------------------------------------------------------------------------
# End-to-end: skill_enquete_stop
# ---------------------------------------------------------------------------


def _seed_state(hooks_dir, session_id, skills, stop_attempts=0):
    save_state(
        state_path(hooks_dir, session_id), {"skills": skills, "stop_attempts": stop_attempts}
    )


def test_e2e_stop_no_state_file_allows_stop(install_hook):
    assert install_hook("skill_enquete_stop").run({"session_id": "sess-1"}).returncode == 0


def test_e2e_stop_missing_session_id_allows_stop(install_hook):
    assert install_hook("skill_enquete_stop").run({}).returncode == 0


def test_e2e_stop_pending_skill_blocks_with_instructions(install_hook):
    hook_ = install_hook("skill_enquete_stop")
    skill_dir = hook_.project / ".claude" / "skills" / "target-skill"
    skill_dir.mkdir(parents=True)
    _seed_state(hook_.hooks_dir, "sess-2", {"target-skill": {"dir": str(skill_dir)}})

    result = hook_.run({"session_id": "sess-2"})
    assert result.returncode == 2
    assert "target-skill" in result.stderr
    assert (skill_dir / "enquete" / "sess-2.md").as_posix() in result.stderr
    assert load_state(state_path(hook_.hooks_dir, "sess-2"))["stop_attempts"] == 1


def test_e2e_stop_already_surveyed_skill_allows_stop(install_hook):
    hook_ = install_hook("skill_enquete_stop")
    skill_dir = hook_.project / ".claude" / "skills" / "target-skill"
    (skill_dir / "enquete").mkdir(parents=True)
    (skill_dir / "enquete" / "sess-3.md").write_text("answered\n", encoding="utf-8")
    _seed_state(hook_.hooks_dir, "sess-3", {"target-skill": {"dir": str(skill_dir)}})
    assert hook_.run({"session_id": "sess-3"}).returncode == 0


def test_e2e_stop_mixed_surveyed_and_pending_only_lists_pending(install_hook):
    hook_ = install_hook("skill_enquete_stop")
    surveyed = hook_.project / ".claude" / "skills" / "surveyed-skill"
    (surveyed / "enquete").mkdir(parents=True)
    (surveyed / "enquete" / "sess-4.md").write_text("done\n", encoding="utf-8")
    pending = hook_.project / ".claude" / "skills" / "pending-skill"
    pending.mkdir(parents=True)
    _seed_state(
        hook_.hooks_dir,
        "sess-4",
        {"surveyed-skill": {"dir": str(surveyed)}, "pending-skill": {"dir": str(pending)}},
    )
    result = hook_.run({"session_id": "sess-4"})
    assert result.returncode == 2
    assert "pending-skill" in result.stderr
    assert "surveyed-skill" not in result.stderr


def test_e2e_stop_max_attempts_reached_gives_up(install_hook):
    hook_ = install_hook("skill_enquete_stop")
    skill_dir = hook_.project / ".claude" / "skills" / "target-skill"
    skill_dir.mkdir(parents=True)
    _seed_state(
        hook_.hooks_dir, "sess-5", {"target-skill": {"dir": str(skill_dir)}}, stop_attempts=3
    )

    result = hook_.run({"session_id": "sess-5"})
    assert result.returncode == 0, result.stderr
    assert "target-skill" in json.loads(result.stdout)["systemMessage"]
    # Giving up must not keep incrementing stop_attempts forever.
    assert load_state(state_path(hook_.hooks_dir, "sess-5"))["stop_attempts"] == 3


def test_e2e_stop_hook_active_does_not_bypass_pending_check(install_hook):
    hook_ = install_hook("skill_enquete_stop")
    skill_dir = hook_.project / ".claude" / "skills" / "target-skill"
    skill_dir.mkdir(parents=True)
    _seed_state(hook_.hooks_dir, "sess-6", {"target-skill": {"dir": str(skill_dir)}})
    result = hook_.run({"session_id": "sess-6", "stop_hook_active": True})
    assert result.returncode == 2
    assert "target-skill" in result.stderr
