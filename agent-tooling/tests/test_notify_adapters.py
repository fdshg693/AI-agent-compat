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

import shutil

import pytest

from agent_tooling.adapters.claude import notify as claude_notify
from agent_tooling.adapters.codex import notify as codex_notify
from agent_tooling.adapters.kilo import notify as kilo_notify

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

    for module in (claude_notify, codex_notify, kilo_notify):
        monkeypatch.setattr(module, "notify_post", post)
        monkeypatch.setattr(module, "notify_remove", remove)
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


@pytest.mark.parametrize(
    ("payload", "title", "body", "sound"),
    [
        (
            _payload(
                "PreToolUse",
                tool_name="request_user_input",
                tool_input={"questions": [{"header": "H", "question": "どれ？"}]},
            ),
            "❓ 質問 [proj]",
            "どれ？",
            "Glass",
        ),
        (
            _payload(
                "PreToolUse",
                tool_name="request_user_input",
                tool_input={"questions": [{"header": "見出し", "question": ""}]},
            ),
            "❓ 質問 [proj]",
            "見出し",
            "Glass",
        ),
        (
            _payload("PreToolUse", tool_name="request_user_input", tool_input={}),
            "❓ 質問 [proj]",
            "回答が必要です",
            "Glass",
        ),
        (
            _payload(
                "PermissionRequest",
                tool_name="Bash",
                tool_input={"description": "ネットワークに接続", "command": "curl x"},
            ),
            "🔐 許可待ち [proj]",
            "ネットワークに接続",
            "Glass",
        ),
        (
            _payload("PermissionRequest", tool_name="Bash", tool_input={"command": "rm -rf b"}),
            "🔐 許可待ち [proj]",
            "Bash: rm -rf b",
            "Glass",
        ),
        (
            _payload("PermissionRequest", tool_name="apply_patch", tool_input={}),
            "🔐 許可待ち [proj]",
            "apply_patch",
            "Glass",
        ),
        (
            _payload(
                "Stop", last_assistant_message="案です\n<proposed_plan>\n1. x\n</proposed_plan>"
            ),
            "📋 プラン確認待ち [proj]",
            "プランを確認してください",
            "Glass",
        ),
        (
            _payload("Stop", last_assistant_message="終わりました"),
            "✅ 完了 [proj]",
            "終わりました",
            "Hero",
        ),
        (
            _payload("Stop", last_assistant_message=None),
            "✅ 完了 [proj]",
            "応答が完了しました",
            "Hero",
        ),
    ],
)
def test_codex_posts(calls, payload, title, body, sound):
    result = codex_notify.handle(payload)
    assert result["action"] == "post"
    ((kind, args, kwargs),) = calls
    assert kind == "post"
    assert args == (title, "/work/proj", body)
    assert kwargs["sound"] == sound
    assert kwargs["notification_id"] == "sid"
    assert kwargs["helper_app"].name == "CodexNotify.app"


@pytest.mark.parametrize(
    "payload",
    [
        _payload("UserPromptSubmit", prompt="次"),
        _payload("PostToolUse", tool_name="request_user_input"),
    ],
)
def test_codex_removes(calls, payload):
    assert codex_notify.handle(payload)["action"] == "remove"
    ((kind, args, kwargs),) = calls
    assert (kind, args) == ("remove", ("sid",))
    assert "timeout" not in kwargs


@pytest.mark.parametrize("event", ["Interrupt", "SessionEnd"])
def test_codex_sync_events_remove_with_short_timeout(calls, event):
    codex_notify.handle(_payload(event))
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
def test_codex_ignores_other_events(calls, payload):
    assert codex_notify.handle(payload) == {"action": "none"}
    assert calls == []


def _run_generated(
    stdin: str, tmp_path: Path, agent: str = "claude"
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # ヘルパー（~/Library/...）を見つけさせない。通知を出さないイベントだけを流す
    env["HOME"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, str(GENERATED / agent / "notify.py")],
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


@pytest.mark.parametrize(
    "stdin",
    [
        json.dumps(_payload("UserPromptSubmit", prompt="hi")),
        json.dumps(_payload("Interrupt")),
        json.dumps(_payload("SessionEnd")),
        json.dumps(_payload("SessionStart")),
        "not json",
        "[]",
    ],
)
def test_codex_generated_prints_nothing_and_exits_zero(stdin, tmp_path):
    result = _run_generated(stdin, tmp_path, "codex")
    assert result.returncode == 0
    assert result.stdout == ""


def _kilo(event: str, *, root: bool = True, **extra) -> dict:
    return {"event": event, "id": "ses_root", "root": root, "cwd": "/work/proj", **extra}


@pytest.mark.parametrize(
    ("payload", "title", "body", "sound"),
    [
        (_kilo("session.status", body="終わりました"), "✅ 完了 [proj]", "終わりました", "Hero"),
        (_kilo("session.status", body="  "), "✅ 完了 [proj]", "応答が完了しました", "Hero"),
        (
            _kilo(
                "permission.asked",
                root=False,
                properties={"permission": "bash", "patterns": ["git push", "-f"]},
            ),
            "🔐 許可待ち [proj]",
            "bash git push -f",
            "Glass",
        ),
        (_kilo("permission.asked", properties={}), "🔐 許可待ち [proj]", "許可が必要です", "Glass"),
        (
            _kilo(
                "question.asked", properties={"questions": [{"question": "進む？", "header": "H"}]}
            ),
            "❓ 質問 [proj]",
            "進む？",
            "Glass",
        ),
        (
            _kilo(
                "question.asked", properties={"questions": [{"question": "", "header": "見出し"}]}
            ),
            "❓ 質問 [proj]",
            "見出し",
            "Glass",
        ),
        (_kilo("question.asked", properties={}), "❓ 質問 [proj]", "回答が必要です", "Glass"),
    ],
)
def test_kilo_posts(calls, payload, title, body, sound):
    result = kilo_notify.handle(payload)
    assert result["action"] == "post"
    ((kind, args, kwargs),) = calls
    assert kind == "post"
    assert args == (title, "/work/proj", body)
    assert kwargs["sound"] == sound
    assert kwargs["notification_id"] == "ses_root"
    assert kwargs["helper_app"].name == "KiloNotify.app"


@pytest.mark.parametrize(
    "payload",
    [
        _kilo("permission.replied", root=False),
        _kilo("question.replied"),
        _kilo("question.rejected", root=False),
        _kilo("chat.message"),
        _kilo("session.deleted"),
    ],
)
def test_kilo_removes(calls, payload):
    assert kilo_notify.handle(payload)["action"] == "remove"
    ((kind, args, kwargs),) = calls
    assert (kind, args) == ("remove", ("ses_root",))
    assert kwargs["helper_app"].name == "KiloNotify.app"


@pytest.mark.parametrize(
    "payload",
    [
        _kilo("session.status", root=False, body="子"),
        _kilo("chat.message", root=False),
        _kilo("session.deleted", root=False),
        _kilo("session.created"),
        {"event": "permission.asked", "root": True, "cwd": "/w"},
    ],
)
def test_kilo_ignores_other_events(calls, payload):
    assert kilo_notify.handle(payload) == {"action": "none"}
    assert calls == []


@pytest.mark.parametrize(
    "stdin",
    [
        json.dumps(_kilo("question.replied")),
        json.dumps(_kilo("chat.message", root=False)),
        json.dumps(_kilo("session.created")),
        "not json",
        "[]",
    ],
)
def test_kilo_generated_prints_nothing_and_exits_zero(stdin, tmp_path):
    result = _run_generated(stdin, tmp_path, "kilo")
    assert result.returncode == 0
    assert result.stdout == ""


def test_kilo_ts_sidecar_contract():
    text = (GENERATED / "kilo" / "notify.ts").read_text(encoding="utf-8")
    assert '"notify.py"' in text
    assert "spawnSync" not in text  # Kilo のイベントループを止めない
    assert '"@kilocode/plugin"' in text
    assert "args" not in text.replace("[script]", "")  # tool の args に触れない


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_kilo_ts_sidecar_behaviour():
    """TS sidecar を node で動かす（Node 22.18+ の型除去で .ts を直接 import する）。"""
    env = os.environ.copy()
    env["KILO_NOTIFY_TS"] = str(GENERATED / "kilo" / "notify.ts")
    result = subprocess.run(
        ["node", "--test", str(Path(__file__).parent / "kilo" / "notify.test.mjs")],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
