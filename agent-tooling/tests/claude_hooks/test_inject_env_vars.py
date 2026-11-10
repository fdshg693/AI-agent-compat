"""inject_env_vars (PreToolUse): YAML subset parsing, @ref resolution, export prefix, e2e."""

from __future__ import annotations

import json

from agent_tooling.adapters.claude import inject_env_vars as hook
from agent_tooling.adapters.claude.common.dotenv import load_dotenv_value

# ---------------------------------------------------------------------------
# parse_env_yaml
# ---------------------------------------------------------------------------


def test_parse_env_yaml_literal_values_and_default_override():
    override, env_vars = hook.parse_env_yaml(
        """
        vars:
          FOO: bar
          BAZ: "quoted value"
          QUX: 'single quoted'
        """.replace("        ", "")
    )
    assert override is False
    assert env_vars == {"FOO": "bar", "BAZ": "quoted value", "QUX": "single quoted"}


def test_parse_env_yaml_override_true_variants():
    for truthy in ("true", "True", "yes", "1", "on"):
        override, _ = hook.parse_env_yaml(f"override: {truthy}\nvars:\n  FOO: bar\n")
        assert override is True, truthy

    for falsy in ("false", "no", "0", "off", ""):
        override, _ = hook.parse_env_yaml(f"override: {falsy}\nvars:\n  FOO: bar\n")
        assert override is False, falsy


def test_parse_env_yaml_ignores_comments_and_blank_lines():
    text = """
# top comment
override: false

vars:
  # a comment inside vars
  FOO: bar

  BAZ: qux
"""
    override, env_vars = hook.parse_env_yaml(text)
    assert override is False
    assert env_vars == {"FOO": "bar", "BAZ": "qux"}


def test_parse_env_yaml_duplicate_nested_keys_last_wins():
    _, env_vars = hook.parse_env_yaml("vars:\n  FOO: first\n  FOO: second\n")
    assert env_vars == {"FOO": "second"}


def test_parse_env_yaml_duplicate_top_level_keys_last_wins():
    override, _ = hook.parse_env_yaml("override: false\noverride: true\nvars:\n  FOO: bar\n")
    assert override is True


def test_parse_env_yaml_duplicate_vars_blocks_last_wins():
    _, env_vars = hook.parse_env_yaml("vars:\n  FOO: first\nvars:\n  FOO: second\n  BAR: baz\n")
    assert env_vars == {"FOO": "second", "BAR": "baz"}


def test_parse_env_yaml_value_containing_colon():
    _, env_vars = hook.parse_env_yaml("vars:\n  DATABASE_URL: postgres://user:pass@host/db\n")
    assert env_vars == {"DATABASE_URL": "postgres://user:pass@host/db"}


def test_parse_env_yaml_at_reference_value_is_kept_verbatim():
    _, env_vars = hook.parse_env_yaml('vars:\n  SECRET: "@secrets/local.env"\n')
    assert env_vars == {"SECRET": "@secrets/local.env"}


def test_parse_env_yaml_no_vars_section():
    override, env_vars = hook.parse_env_yaml("override: true\n")
    assert override is True
    assert env_vars == {}


# ---------------------------------------------------------------------------
# load_dotenv_value (common/dotenv.py)
# ---------------------------------------------------------------------------


def test_load_dotenv_value_found(tmp_path):
    p = tmp_path / "local.env"
    p.write_text('# comment\nFOO=bar\nBAZ="qux"\n', encoding="utf-8")
    assert load_dotenv_value(p, "FOO") == "bar"
    assert load_dotenv_value(p, "BAZ") == "qux"


def test_load_dotenv_value_missing_key(tmp_path):
    p = tmp_path / "local.env"
    p.write_text("FOO=bar\n", encoding="utf-8")
    assert load_dotenv_value(p, "NOPE") is None


def test_load_dotenv_value_missing_file(tmp_path):
    assert load_dotenv_value(tmp_path / "nope.env", "FOO") is None


def test_load_dotenv_value_duplicate_keys_last_wins(tmp_path):
    p = tmp_path / "local.env"
    p.write_text("FOO=first\nFOO=second\n", encoding="utf-8")
    assert load_dotenv_value(p, "FOO") == "second"


# ---------------------------------------------------------------------------
# resolve_value
# ---------------------------------------------------------------------------


def test_resolve_value_literal_passthrough(tmp_path):
    warnings = []
    assert hook.resolve_value("FOO", "bar", tmp_path, warnings) == "bar"
    assert warnings == []


def test_resolve_value_at_reference_success(tmp_path):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "local.env").write_text("FOO=resolved\n", encoding="utf-8")
    warnings = []
    assert hook.resolve_value("FOO", "@secrets/local.env", tmp_path, warnings) == "resolved"
    assert warnings == []


def test_resolve_value_at_reference_missing_key_warns(tmp_path):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "local.env").write_text("OTHER=x\n", encoding="utf-8")
    warnings = []
    assert hook.resolve_value("FOO", "@secrets/local.env", tmp_path, warnings) is None
    assert len(warnings) == 1
    assert "FOO" in warnings[0]


def test_resolve_value_at_reference_missing_file_warns(tmp_path):
    warnings = []
    assert hook.resolve_value("FOO", "@secrets/nope.env", tmp_path, warnings) is None
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# build_export_prefix
# ---------------------------------------------------------------------------


def test_build_export_prefix_bash_escapes_single_quotes():
    assert (
        hook.build_export_prefix("Bash", {"FOO": "it's a test"}) == "export FOO='it'\\''s a test'"
    )


def test_build_export_prefix_powershell_escapes_single_quotes():
    assert (
        hook.build_export_prefix("PowerShell", {"FOO": "it's a test"}) == "$env:FOO='it''s a test'"
    )


def test_build_export_prefix_multiple_vars_preserves_order():
    assert hook.build_export_prefix("Bash", {"A": "1", "B": "2"}) == "export A='1'\nexport B='2'"


# ---------------------------------------------------------------------------
# End-to-end: generated hook installed in <project>/.claude/hooks/
# ---------------------------------------------------------------------------


def _payload(tool_name, command):
    return {"tool_name": tool_name, "tool_input": {"command": command}}


def test_e2e_no_config_is_noop(install_hook):
    hook_ = install_hook("inject_env_vars")
    result = hook_.run(_payload("Bash", "echo hi"))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_e2e_non_command_tool_is_noop(install_hook):
    hook_ = install_hook("inject_env_vars")
    (hook_.config_dir / "inject_env_vars.yaml").write_text("vars:\n  FOO: bar\n", encoding="utf-8")
    result = hook_.run(_payload("Read", "n/a"))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_e2e_injects_literal_and_at_reference_bash(install_hook):
    hook_ = install_hook("inject_env_vars")
    config_dir = hook_.config_dir
    (config_dir / "secrets").mkdir()
    (config_dir / "secrets" / "local.env").write_text("FROM_FILE=secret-value\n", encoding="utf-8")
    (config_dir / "inject_env_vars.yaml").write_text(
        'override: false\nvars:\n  LITERAL_VAR: hello-world\n  FROM_FILE: "@secrets/local.env"\n',
        encoding="utf-8",
    )

    result = hook_.run(_payload("Bash", "echo test"))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    command = output["hookSpecificOutput"]["updatedInput"]["command"]
    assert "export LITERAL_VAR='hello-world'" in command
    assert "export FROM_FILE='secret-value'" in command
    assert command.endswith("echo test")
    assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
    # Notification of injected keys is on by default.
    assert "LITERAL_VAR" in output["systemMessage"]
    assert "FROM_FILE" in output["systemMessage"]


def test_e2e_config_is_read_next_to_the_hook_not_from_project(install_hook, tmp_path):
    hook_ = install_hook("inject_env_vars")
    (hook_.config_dir / "inject_env_vars.yaml").write_text("vars:\n  FOO: bar\n", encoding="utf-8")
    # A different project dir must not change where the hook finds its config.
    other = tmp_path / "elsewhere"
    other.mkdir()
    result = hook_.run(_payload("Bash", "echo test"), env={"CLAUDE_PROJECT_DIR": str(other)})
    assert (
        "export FOO='bar'"
        in json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]["command"]
    )


def test_e2e_notify_disabled_suppresses_message(install_hook):
    hook_ = install_hook("inject_env_vars")
    (hook_.config_dir / "inject_env_vars.yaml").write_text(
        "vars:\n  LITERAL_VAR: hello-world\n", encoding="utf-8"
    )
    result = hook_.run(_payload("Bash", "echo test"), env={"NOTIFY_INJECTED_VARS": "false"})
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert (
        "export LITERAL_VAR='hello-world'"
        in output["hookSpecificOutput"]["updatedInput"]["command"]
    )
    assert "systemMessage" not in output


def test_e2e_notify_disabled_via_hook_dotenv(install_hook):
    hook_ = install_hook("inject_env_vars")
    (hook_.config_dir / "inject_env_vars.yaml").write_text("vars:\n  FOO: bar\n", encoding="utf-8")
    (hook_.hooks_dir / ".env").write_text("NOTIFY_INJECTED_VARS=false\n", encoding="utf-8")
    output = json.loads(hook_.run(_payload("Bash", "echo test")).stdout)
    assert "systemMessage" not in output


def test_e2e_default_override_false_skips_existing_env_var(install_hook):
    hook_ = install_hook("inject_env_vars")
    (hook_.config_dir / "inject_env_vars.yaml").write_text(
        "override: false\nvars:\n  ALREADY_SET: new-value\n", encoding="utf-8"
    )
    result = hook_.run(_payload("Bash", "echo test"), env={"ALREADY_SET": "old-value"})
    assert result.returncode == 0
    # Nothing left to inject -> no updatedInput, command is untouched by the hook.
    assert result.stdout.strip() == ""


def test_e2e_override_true_overwrites_existing_env_var(install_hook):
    hook_ = install_hook("inject_env_vars")
    (hook_.config_dir / "inject_env_vars.yaml").write_text(
        "override: true\nvars:\n  ALREADY_SET: new-value\n", encoding="utf-8"
    )
    result = hook_.run(_payload("Bash", "echo test"), env={"ALREADY_SET": "old-value"})
    assert result.returncode == 0
    command = json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]["command"]
    assert "export ALREADY_SET='new-value'" in command


def test_e2e_missing_reference_warns_but_does_not_block(install_hook):
    hook_ = install_hook("inject_env_vars")
    (hook_.config_dir / "inject_env_vars.yaml").write_text(
        'vars:\n  LITERAL_VAR: kept\n  MISSING: "@secrets/nope.env"\n', encoding="utf-8"
    )
    result = hook_.run(_payload("Bash", "echo test"))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    command = output["hookSpecificOutput"]["updatedInput"]["command"]
    assert "export LITERAL_VAR='kept'" in command
    assert "MISSING" not in command
    assert "MISSING" in output["systemMessage"]


def test_e2e_powershell_uses_env_syntax(install_hook):
    hook_ = install_hook("inject_env_vars")
    (hook_.config_dir / "inject_env_vars.yaml").write_text("vars:\n  FOO: bar\n", encoding="utf-8")
    result = hook_.run(_payload("PowerShell", "Get-ChildItem"))
    assert result.returncode == 0
    command = json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]["command"]
    assert command == "$env:FOO='bar'\nGet-ChildItem"
