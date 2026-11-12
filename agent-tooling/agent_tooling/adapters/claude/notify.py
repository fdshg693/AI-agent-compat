#!/usr/bin/env python3
"""Claude Code adapter for the ``notify`` scenario: posts a per-session
notification when Claude needs the user, and removes it once the user responds.
One artifact is registered for every event below; the branch is chosen from
``hook_event_name``.

Post (title = ``<label> [<cwd folder>]``, subtitle = cwd with ``~``):

- ``PreToolUse`` AskUserQuestion: ❓ 質問 / the first question / sound Glass
- ``PreToolUse`` ExitPlanMode: 📋 プラン承認待ち / sound Glass
- ``PermissionRequest``: 🔐 許可待ち / ``<tool>: <command|file_path|url>`` / sound Glass
- ``Notification`` (elicitation dialogs): 🔔 ``<title>`` / ``<message>`` / sound Glass
- ``Stop``: ✅ 完了 / ``last_assistant_message`` / sound Hero

Remove: ``UserPromptSubmit``, ``PostToolUse`` (AskUserQuestion / ExitPlanMode),
``SessionEnd`` (helper call capped at 2 seconds; the hook is synchronous).

The notification identifier is ``session_id``, so each session keeps only its
latest notification. Posting/removing needs the ClaudeNotify helper .app on
macOS (``just --justfile agent-compat/agent-tooling/justfile
notify-helper-mac claude``); without it posts fall back to ``osascript`` and
removes do nothing. Other OSes (including Windows) do nothing -- use
``stop_alert`` there. Do not register both ``notify`` and ``stop_alert``:
Stop would notify twice.

Prints nothing (``UserPromptSubmit`` stdout would enter Claude's context) and
always exits 0.

環境変数（省略可）:
- `HOOK_LOG`  このフックのデバッグログを配置先ディレクトリの `logs/notify/` に書き出すかどうか
              （true/false等）。未設定ならスクリプト先頭の `ENABLE_HOOK_LOG` に従う。
              配置先ディレクトリの `.env` に設定されていればそちらが優先。
"""

import json
import os
import sys

from agent_tooling.notify import (
    format_title,
    mac_helper_app,
    notify_post,
    notify_remove,
    shorten_home,
)

from .common.hook_log import is_log_enabled
from .common.runtime import make_finish

# Debug-log ON/OFF only (writes to logs/notify/ next to this hook).
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

# macOS の通知ヘルパー（`notify-helper-mac claude` でビルドする .app の名前）
MAC_HELPER_NAME = "ClaudeNotify"
# 同期フック（SessionEnd）でヘルパーを打ち切る秒数
SYNC_REMOVE_TIMEOUT = 2.0

SOUND_ATTENTION = "Glass"
SOUND_DONE = "Hero"

REMOVE_EVENTS = ("UserPromptSubmit", "PostToolUse")
SYNC_REMOVE_EVENTS = ("SessionEnd",)


def _tool_input(payload: dict) -> dict:
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def _first_question(tool_input: dict) -> str:
    questions = tool_input.get("questions")
    if isinstance(questions, list) and questions and isinstance(questions[0], dict):
        question = questions[0].get("question")
        if isinstance(question, str):
            return question
    return "回答が必要です"


def _describe_tool(name: str, tool_input: dict) -> str:
    for key in ("command", "file_path", "url"):
        detail = tool_input.get(key)
        if isinstance(detail, str) and detail:
            return f"{name}: {detail}"
    return name


def build_notification(payload: dict) -> tuple[str, str, str] | None:
    """イベントから `(label, body, sound)` を決める。通知しないイベントなら None。"""
    event = payload.get("hook_event_name") or ""
    if event == "PreToolUse":
        tool = payload.get("tool_name") or ""
        if tool == "AskUserQuestion":
            return "❓ 質問", _first_question(_tool_input(payload)), SOUND_ATTENTION
        if tool == "ExitPlanMode":
            return "📋 プラン承認待ち", "プランを確認してください", SOUND_ATTENTION
        return None
    if event == "PermissionRequest":
        tool = str(payload.get("tool_name") or "")
        return "🔐 許可待ち", _describe_tool(tool, _tool_input(payload)), SOUND_ATTENTION
    if event == "Notification":
        label = str(payload.get("title") or "") or "入力待ち"
        return f"🔔 {label}", str(payload.get("message") or ""), SOUND_ATTENTION
    if event == "Stop":
        body = str(payload.get("last_assistant_message") or "") or "応答が完了しました"
        return "✅ 完了", body, SOUND_DONE
    return None


def handle(payload: dict) -> dict:
    """1 イベントを処理し、ログ用の結果を返す。"""
    event = payload.get("hook_event_name") or ""
    session_id = str(payload.get("session_id") or "")
    helper_app = mac_helper_app(MAC_HELPER_NAME)

    if event in REMOVE_EVENTS:
        return {"action": "remove", "result": notify_remove(session_id, helper_app=helper_app)}
    if event in SYNC_REMOVE_EVENTS:
        result = notify_remove(session_id, helper_app=helper_app, timeout=SYNC_REMOVE_TIMEOUT)
        return {"action": "remove", "result": result}

    built = build_notification(payload)
    if built is None:
        return {"action": "none"}
    label, body, sound = built
    cwd = str(payload.get("cwd") or "") or os.getcwd()
    result = notify_post(
        format_title(label, cwd),
        shorten_home(cwd),
        body,
        sound=sound,
        notification_id=session_id,
        helper_app=helper_app,
    )
    return {"action": "post", "result": result}


def main():
    log = {}
    finish = make_finish(SCRIPT_NAME, log, is_log_enabled(ENABLE_HOOK_LOG))
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        finish(0, reason="unparsable stdin")
    if not isinstance(payload, dict):
        finish(0, reason="payload is not an object")
    log["event"] = payload.get("hook_event_name")
    try:
        log.update(handle(payload))
    except Exception as exc:
        log["error"] = str(exc)
    finish(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
