"""Agent-session adapter contracts: stdin payload -> registry side effects."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from agent_tooling.core import sessions

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "agent_tooling"
GENERATED = PACKAGE_ROOT / "hooks" / "generated"


def run_session(agent: str, payload: dict, directory: Path) -> tuple[int, str]:
    script = GENERATED / agent / "agent_sessions.py"
    env = os.environ.copy()
    env[sessions.DIRECTORY_ENV] = str(directory)
    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return result.returncode, result.stdout


def entries(directory: Path):
    return sessions.list_entries(str(directory))


def test_claude_start_cwd_end(tmp_path: Path):
    reg = tmp_path / "reg"
    code, stdout = run_session(
        "claude",
        {"hook_event_name": "SessionStart", "session_id": "s1", "cwd": "/work"},
        reg,
    )
    assert code == 0
    assert stdout == ""
    started = entries(reg)
    assert len(started) == 1
    assert started[0]["agent"] == "claude"
    assert started[0]["session_id"] == "s1"
    assert started[0]["cwd"] == "/work"
    assert started[0]["hook_event"] == "SessionStart"
    assert started[0]["pid_source"] in ("agent", "unknown")
    if started[0]["pid_source"] == "agent":
        assert started[0]["pid"] > 0

    code, stdout = run_session(
        "claude",
        {
            "hook_event_name": "CwdChanged",
            "session_id": "s1",
            "cwd": "/work",
            "new_cwd": "/work/sub",
        },
        reg,
    )
    assert code == 0 and stdout == ""
    assert entries(reg)[0]["cwd"] == "/work/sub"

    code, stdout = run_session("claude", {"hook_event_name": "SessionEnd", "session_id": "s1"}, reg)
    assert code == 0 and stdout == ""
    assert entries(reg) == []


def test_claude_end_without_start_is_noop(tmp_path: Path):
    reg = tmp_path / "reg"
    code, _ = run_session("claude", {"hook_event_name": "SessionEnd", "session_id": "ghost"}, reg)
    assert code == 0
    assert entries(reg) == []


def test_codex_start_and_end_are_silent(tmp_path: Path):
    reg = tmp_path / "reg"
    code, stdout = run_session(
        "codex",
        {"hook_event_name": "SessionStart", "session_id": "c1", "cwd": "/repo"},
        reg,
    )
    assert code == 0 and stdout == ""
    assert entries(reg)[0]["agent"] == "codex"
    assert entries(reg)[0]["cwd"] == "/repo"

    code, stdout = run_session("codex", {"hook_event_name": "SessionEnd", "session_id": "c1"}, reg)
    assert code == 0 and stdout == ""
    assert entries(reg) == []


def test_cursor_uses_workspace_roots(tmp_path: Path):
    reg = tmp_path / "reg"
    code, stdout = run_session(
        "cursor",
        {
            "hook_event_name": "sessionStart",
            "session_id": "cur1",
            "workspace_roots": ["/ws"],
        },
        reg,
    )
    assert code == 0 and stdout == ""
    assert entries(reg)[0]["cwd"] == "/ws"

    code, _ = run_session("cursor", {"hook_event_name": "sessionEnd", "session_id": "cur1"}, reg)
    assert code == 0
    assert entries(reg) == []


def test_cursor_conversation_id_fallback(tmp_path: Path):
    reg = tmp_path / "reg"
    code, _ = run_session(
        "cursor",
        {
            "hook_event_name": "sessionStart",
            "conversation_id": "conv-1",
            "workspace_roots": ["/ws2"],
        },
        reg,
    )
    assert code == 0
    assert entries(reg)[0]["session_id"] == "conv-1"


def test_antigravity_pseudo_lifecycle(tmp_path: Path):
    reg = tmp_path / "reg"
    code, stdout = run_session(
        "antigravity",
        {"conversationId": "ag1", "workspacePaths": ["/ws"], "invocationNum": 0},
        reg,
    )
    assert code == 0
    assert json.loads(stdout) == {}
    assert entries(reg)[0]["agent"] == "antigravity"
    assert entries(reg)[0]["cwd"] == "/ws"
    assert entries(reg)[0]["hook_event"] == "PreInvocation"

    code, stdout = run_session(
        "antigravity",
        {"conversationId": "ag1", "workspacePaths": ["/ws"], "invocationNum": 1},
        reg,
    )
    assert code == 0 and json.loads(stdout) == {}
    assert len(entries(reg)) == 1

    code, stdout = run_session(
        "antigravity",
        {"conversationId": "ag1", "toolCall": {"args": {"Cwd": "/ws/dir"}}},
        reg,
    )
    assert code == 0
    assert json.loads(stdout) == {"decision": "allow"}
    assert entries(reg)[0]["cwd"] == "/ws/dir"

    code, stdout = run_session(
        "antigravity",
        {"conversationId": "ag1", "fullyIdle": False, "terminationReason": "x"},
        reg,
    )
    assert code == 0 and json.loads(stdout) == {}
    assert len(entries(reg)) == 1

    code, stdout = run_session(
        "antigravity",
        {"conversationId": "ag1", "fullyIdle": True, "terminationReason": "idle"},
        reg,
    )
    assert code == 0 and json.loads(stdout) == {}
    assert entries(reg) == []


def test_antigravity_unknown_payload_returns_allow(tmp_path: Path):
    reg = tmp_path / "reg"
    code, stdout = run_session("antigravity", {"unexpected": True}, reg)
    assert code == 0
    assert json.loads(stdout) == {"decision": "allow"}


def test_kilo_helper_actions(tmp_path: Path):
    reg = tmp_path / "reg"
    code, stdout = run_session(
        "kilo",
        {
            "action": "start",
            "session_id": "k1",
            "cwd": "/k",
            "pid": os.getpid(),
            "pid_source": "host",
        },
        reg,
    )
    assert code == 0 and stdout == ""
    started = entries(reg)[0]
    assert started["agent"] == "kilo"
    assert started["pid_source"] == "host"
    assert sessions.is_live(started) is True

    run_session(
        "kilo",
        {"action": "cwd", "session_id": "k1", "cwd": "/k/sub", "pid_source": "host"},
        reg,
    )
    assert entries(reg)[0]["cwd"] == "/k/sub"

    run_session(
        "kilo",
        {"action": "end", "session_id": "k1", "pid_source": "host"},
        reg,
    )
    assert entries(reg) == []


def test_kilo_ignores_unknown_action(tmp_path: Path):
    reg = tmp_path / "reg"
    code, _ = run_session("kilo", {"action": "idle", "session_id": "k2", "pid_source": "host"}, reg)
    assert code == 0
    assert entries(reg) == []


def test_kilo_ts_event_contract():
    text = (GENERATED / "kilo" / "agent_sessions.ts").read_text(encoding="utf-8")
    assert "spawnSync" in text
    assert "session.created" in text
    assert "session.deleted" in text
    assert "session.updated" in text
    assert "process.pid" in text
    assert '"host"' in text
    assert "agent_sessions.py" in text
    assert "session.idle" not in text
    assert "throw" not in text


def test_all_adapters_exist():
    for agent in ("claude", "codex", "cursor", "antigravity", "kilo"):
        assert (GENERATED / agent / "agent_sessions.py").is_file()
