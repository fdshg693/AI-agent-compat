"""Remaining Claude-only hooks and the install-location path contract (common/paths.py)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agent_tooling.adapters.claude.common import paths, play_alert_sound, show_alert_popup
from agent_tooling.adapters.claude.common.long_run_state import load_state, session_paths

# ---------------------------------------------------------------------------
# common/paths.py
# ---------------------------------------------------------------------------


def test_resolve_project_dir_prefers_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "env"))
    assert paths.resolve_project_dir({"cwd": str(tmp_path / "cwd")}) == tmp_path / "env"


def test_resolve_project_dir_falls_back_to_payload_cwd(tmp_path, clean_hook_env):
    assert paths.resolve_project_dir({"cwd": str(tmp_path)}) == tmp_path


def test_resolve_project_dir_falls_back_to_git_toplevel(tmp_path, clean_hook_env, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.chdir(repo / "sub")
    assert paths.resolve_project_dir().resolve() == repo.resolve()


def test_generated_hook_writes_debug_log_next_to_itself(install_hook, tmp_path):
    hook_ = install_hook("block_large_read")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = hook_.run(
        {"tool_name": "Bash"}, env={"HOOK_LOG": "true", "CLAUDE_PROJECT_DIR": str(elsewhere)}
    )
    assert result.returncode == 0
    logs = list((hook_.hooks_dir / "logs" / "block_large_read").glob("*.log"))
    assert len(logs) == 1
    assert json.loads(logs[0].read_text(encoding="utf-8"))["reason"] == "not a Read call"
    assert not (elsewhere / ".claude").exists()


# ---------------------------------------------------------------------------
# block_large_read
# ---------------------------------------------------------------------------


def test_block_large_read_blocks_over_threshold(install_hook):
    hook_ = install_hook("block_large_read")
    big = hook_.project / "big.txt"
    big.write_text("x" * 100 + "\n" * 1 + ("y" * 100 + "\n") * 30, encoding="utf-8")
    result = hook_.run({"tool_name": "Read", "tool_input": {"file_path": str(big)}})
    assert result.returncode == 2
    assert "サブエージェント" in result.stderr


def test_block_large_read_passes_small_file(install_hook):
    hook_ = install_hook("block_large_read")
    small = hook_.project / "small.txt"
    small.write_text("hello\n", encoding="utf-8")
    result = hook_.run({"tool_name": "Read", "tool_input": {"file_path": str(small)}})
    assert result.returncode == 0
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# long_run_collector / long_run_statement_collector
# ---------------------------------------------------------------------------


def _tool_payload(event, tool="Bash", session_id="sess-1"):
    return {
        "hook_event_name": event,
        "tool_name": tool,
        "tool_input": {"command": "ls"},
        "session_id": session_id,
    }


def test_long_run_collector_nudges_on_failure_streak(install_hook):
    hook_ = install_hook("long_run_collector")
    env = {"LONG_RUN_FAILURE_STREAK_THRESHOLD": "2", "LONG_RUN_OP_THRESHOLD": "100"}
    first = hook_.run(_tool_payload("PostToolUseFailure"), env=env)
    assert first.returncode == 0 and first.stdout == ""
    second = hook_.run(_tool_payload("PostToolUseFailure"), env=env)
    output = json.loads(second.stdout)
    assert output["decision"] == "block"
    assert "2回連続" in output["reason"]

    state_file, log_file = session_paths(hook_.hooks_dir, "sess-1")
    assert state_file.parent == hook_.hooks_dir / "state" / "long_run"
    assert load_state(state_file)["failure_streak"] == 0
    assert len(log_file.read_text(encoding="utf-8").splitlines()) == 2


def test_long_run_pair_share_state_and_log(install_hook, tmp_path):
    collector = install_hook("long_run_collector")
    statement = install_hook("long_run_statement_collector")
    assert collector.hooks_dir == statement.hooks_dir
    collector.run(_tool_payload("PostToolUse", session_id="sess-2"))

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}}
        )
        + "\n",
        encoding="utf-8",
    )
    payload = {"session_id": "sess-2", "transcript_path": str(transcript)}
    assert statement.run(payload).returncode == 0
    assert statement.run(payload).returncode == 0  # re-fire must not re-log

    state_file, log_file = session_paths(collector.hooks_dir, "sess-2")
    records = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert [r["type"] for r in records] == ["command", "statement"]
    assert load_state(state_file)["transcript_offset"] == 1


# ---------------------------------------------------------------------------
# task_tracker_session
# ---------------------------------------------------------------------------


def _expansion(args, session_id="sess-1", **extra):
    return {
        "command_name": "task-tracker",
        "expansion_type": "slash_command",
        "command_args": args,
        "session_id": session_id,
        **extra,
    }


def test_task_tracker_records_session_under_project(install_hook):
    hook_ = install_hook("task_tracker_session")
    assert hook_.run(_expansion("my-task")).returncode == 0
    assert hook_.run(_expansion("my-task")).returncode == 0  # duplicate not appended
    sessions = hook_.project / ".claude" / "tasks" / "my-task" / "sessions.md"
    lines = sessions.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# task-tracker sessions: my-task"
    assert [line for line in lines if line.startswith("- ")][0].endswith(" sess-1")
    assert len([line for line in lines if line.startswith("- ")]) == 1


def test_task_tracker_uses_payload_cwd_without_project_env(install_hook, tmp_path):
    hook_ = install_hook("task_tracker_session")
    other = tmp_path / "other-project"
    other.mkdir()
    result = hook_.run(_expansion("t1", cwd=str(other)), project_env=False)
    assert result.returncode == 0
    assert (other / ".claude" / "tasks" / "t1" / "sessions.md").is_file()


def test_task_tracker_invalid_name_warns(install_hook):
    hook_ = install_hook("task_tracker_session")
    result = hook_.run(_expansion("-bad"))
    assert result.returncode == 0
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "-bad" in context
    assert not (hook_.project / ".claude" / "tasks").exists()


# ---------------------------------------------------------------------------
# aim-based hooks fall through when `aim` is not on PATH
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hook_id", "payload"),
    [
        (
            "summarize_read",
            {
                "tool_name": "Read",
                "tool_response": {"type": "text", "file": {"content": "x" * 10000}},
            },
        ),
        ("summarize_webfetch", {"tool_name": "WebFetch", "tool_response": {"result": "x" * 10000}}),
        ("translate_prompt", {"hook_event_name": "UserPromptSubmit", "prompt": "こんにちは"}),
    ],
)
def test_aim_hooks_noop_without_aim(install_hook, tmp_path, hook_id, payload):
    hook_ = install_hook(hook_id)
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    result = hook_.run(payload, env={"PATH": str(empty_path)})
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# stop_alert (+ common/play_alert_sound.py, common/show_alert_popup.py)
# ---------------------------------------------------------------------------


def test_stop_alert_skips_when_stop_hook_active(install_hook):
    hook_ = install_hook("stop_alert")
    result = hook_.run({"stop_hook_active": True}, env={"HOOK_LOG": "true"})
    assert result.returncode == 0
    (log,) = (hook_.hooks_dir / "logs" / "stop_alert").glob("*.log")
    assert json.loads(log.read_text(encoding="utf-8"))["reason"] == "stop_hook_active, skipped"


def test_stop_alert_does_nothing_when_disabled(install_hook):
    hook_ = install_hook("stop_alert")
    env = {"HOOK_LOG": "true", "STOP_ALERT_SOUND_ENABLED": "false", "STOP_ALERT_POPUP": "false"}
    assert hook_.run({}, env=env).returncode == 0
    (log,) = (hook_.hooks_dir / "logs" / "stop_alert").glob("*.log")
    record = json.loads(log.read_text(encoding="utf-8"))
    assert record["reason"] == "played"
    assert record["sound"]["mode"] in {"disabled", "unsupported"}
    assert record["popup"]["mode"] in {"disabled", "unsupported"}


def test_resolve_sound_path_prefers_env_then_hook_dir(tmp_path, monkeypatch):
    wav = tmp_path / "custom.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setenv("STOP_ALERT_SOUND", str(wav))
    assert play_alert_sound.resolve_sound_path() == wav

    monkeypatch.delenv("STOP_ALERT_SOUND")
    monkeypatch.setattr(play_alert_sound, "hook_dir", lambda: tmp_path)
    assert play_alert_sound.resolve_sound_path() is None
    (tmp_path / "alert.wav").write_bytes(b"RIFF")
    assert play_alert_sound.resolve_sound_path() == tmp_path / "alert.wav"


def test_show_popup_respawns_running_hook_with_popup_flag(monkeypatch, clean_hook_env):
    """After inlining, show_popup's own module file no longer exists: it must
    re-run the entry script (sys.argv[0]) with --popup, not ``__file__``."""
    spawned = []
    monkeypatch.setattr(show_alert_popup.sys, "platform", "win32")
    monkeypatch.setattr(show_alert_popup.sys, "argv", ["C:/hooks/stop_alert.py"])
    monkeypatch.setattr(show_alert_popup.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(show_alert_popup.subprocess, "CREATE_NEW_PROCESS_GROUP", 0, raising=False)
    monkeypatch.setattr(
        show_alert_popup.subprocess, "Popen", lambda argv, **kwargs: spawned.append(argv)
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/work/my-project")

    result = show_alert_popup.show_popup(text="hi", seconds=5)
    assert result["ok"] is True
    (argv,) = spawned
    assert argv[0] == sys.executable
    assert Path(argv[1]) == Path("C:/hooks/stop_alert.py").resolve()
    assert argv[2:] == [show_alert_popup.POPUP_FLAG, "hi", "5", "my-project"]
