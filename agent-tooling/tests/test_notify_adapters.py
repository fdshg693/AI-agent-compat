"""scenario `notify` のアダプタ: イベントごとに「出す／消す／何もしない」と通知の内容。

実際の通知は出さない（アダプタが import した `notify_post`／`notify_remove` を差し替える）。
生成物の実行は、通知を出さないイベント（消す・対象外）だけで確かめる。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_tooling.adapters.claude import notify as claude_notify

GENERATED = Path(__file__).resolve().parents[1] / "agent_tooling" / "hooks" / "generated"


@pytest.fixture
def calls(monkeypatch):
    recorded: list[tuple[str, tuple, dict]] = []

    def post(*args, **kwargs):
        recorded.append(("post", args, kwargs))
        return {"ok": True, "mode": "fake"}

    def remove(*args, **kwargs):
        recorded.append(("remove", args, kwargs))
        return {"ok": True, "mode": "fake"}

    monkeypatch.setattr(claude_notify, "notify_post", post)
    monkeypatch.setattr(claude_notify, "notify_remove", remove)
    return recorded


def _payload(event: str, **extra) -> dict:
    return {"hook_event_name": event, "session_id": "sid", "cwd": "/work/proj", **extra}


@pytest.mark.parametrize(
    ("payload", "title", "body", "sound"),
    [
        (
            _payload(
                "PreToolUse",
                tool_name="AskUserQuestion",
                tool_input={"questions": [{"question": "どれ？"}, {"question": "次"}]},
            ),
            "❓ 質問 [proj]",
            "どれ？",
            "Glass",
        ),
        (
            _payload("PreToolUse", tool_name="AskUserQuestion", tool_input={}),
            "❓ 質問 [proj]",
            "回答が必要です",
            "Glass",
        ),
        (
            _payload("PreToolUse", tool_name="ExitPlanMode"),
            "📋 プラン承認待ち [proj]",
            "プランを確認してください",
            "Glass",
        ),
        (
            _payload("PermissionRequest", tool_name="Bash", tool_input={"command": "ls -la"}),
            "🔐 許可待ち [proj]",
            "Bash: ls -la",
            "Glass",
        ),
        (
            _payload("PermissionRequest", tool_name="Edit", tool_input={"file_path": "/a.py"}),
            "🔐 許可待ち [proj]",
            "Edit: /a.py",
            "Glass",
        ),
        (
            _payload("PermissionRequest", tool_name="WebFetch", tool_input={"url": "https://x"}),
            "🔐 許可待ち [proj]",
            "WebFetch: https://x",
            "Glass",
        ),
        (
            _payload("PermissionRequest", tool_name="Task", tool_input={}),
            "🔐 許可待ち [proj]",
            "Task",
            "Glass",
        ),
        (
            _payload("Notification", title="MCP", message="入力してください"),
            "🔔 MCP [proj]",
            "入力してください",
            "Glass",
        ),
        (_payload("Notification", message="m"), "🔔 入力待ち [proj]", "m", "Glass"),
        (
            _payload("Stop", last_assistant_message="終わりました"),
            "✅ 完了 [proj]",
            "終わりました",
            "Hero",
        ),
        (_payload("Stop"), "✅ 完了 [proj]", "応答が完了しました", "Hero"),
    ],
)
def test_claude_posts(calls, payload, title, body, sound):
    result = claude_notify.handle(payload)
    assert result["action"] == "post"
    ((kind, args, kwargs),) = calls
    assert kind == "post"
    assert args == (title, "/work/proj", body)
    assert kwargs["sound"] == sound
    assert kwargs["notification_id"] == "sid"
    assert kwargs["helper_app"].name == "ClaudeNotify.app"


def test_claude_post_subtitle_shortens_home(calls):
    home = os.path.expanduser("~")
    claude_notify.handle({"hook_event_name": "Stop", "session_id": "s", "cwd": home + "/w"})
    assert calls[0][1][1] == "~/w"


@pytest.mark.parametrize(
    "payload",
    [
        _payload("UserPromptSubmit", prompt="次"),
        _payload("PostToolUse", tool_name="AskUserQuestion"),
        _payload("PostToolUse", tool_name="ExitPlanMode"),
    ],
)
def test_claude_removes(calls, payload):
    assert claude_notify.handle(payload)["action"] == "remove"
    ((kind, args, kwargs),) = calls
    assert (kind, args) == ("remove", ("sid",))
    assert "timeout" not in kwargs


def test_claude_session_end_removes_with_short_timeout(calls):
    claude_notify.handle(_payload("SessionEnd", reason="clear"))
    ((kind, args, kwargs),) = calls
    assert (kind, args) == ("remove", ("sid",))
    assert kwargs["timeout"] == 2.0


@pytest.mark.parametrize(
    "payload",
    [
        _payload("PreToolUse", tool_name="Bash"),
        _payload("SessionStart"),
        {"session_id": "sid"},
    ],
)
def test_claude_ignores_other_events(calls, payload):
    assert claude_notify.handle(payload) == {"action": "none"}
    assert calls == []


def _run_generated(stdin: str, tmp_path: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # ヘルパー（~/Library/...）を見つけさせない。通知を出さないイベントだけを流す
    env["HOME"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, str(GENERATED / "claude" / "notify.py")],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=30,
    )


@pytest.mark.parametrize(
    "stdin",
    [
        json.dumps(_payload("UserPromptSubmit", prompt="hi")),
        json.dumps(_payload("SessionEnd")),
        json.dumps(_payload("SessionStart")),
        "not json",
        "[]",
    ],
)
def test_claude_generated_prints_nothing_and_exits_zero(stdin, tmp_path):
    result = _run_generated(stdin, tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""
