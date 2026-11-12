#!/usr/bin/env python3
"""Codex adapter for the ``notify`` scenario: posts a per-session notification
when Codex needs the user, and removes it once the user responds. One artifact
is registered for every event below; the branch is chosen from
``hook_event_name``.

Post (title = ``<label> [<cwd folder>]``, subtitle = cwd with ``~``):

- ``PreToolUse`` request_user_input: ❓ 質問 / the first question (its header
  when empty) / sound Glass
- ``PermissionRequest``: 🔐 許可待ち / ``description``, else
  ``<tool>: <command>``, else the tool name / sound Glass
- ``Stop``: 📋 プラン確認待ち (sound Glass) when the last reply contains
  ``<proposed_plan>``, else ✅ 完了 / ``last_assistant_message`` (sound Hero)

Remove: ``UserPromptSubmit``, ``PostToolUse`` (request_user_input),
``Interrupt`` and ``SessionEnd`` (helper call capped at 2 seconds; both hooks
are synchronous with a 3 second timeout).

The notification identifier is ``session_id`` (subagent hooks carry the parent
ID), so each session keeps only its latest notification. Posting/removing needs
the CodexNotify helper .app on macOS (``just --justfile
agent-compat/agent-tooling/justfile notify-helper-mac codex``); without it
posts fall back to ``osascript`` and removes do nothing. Other OSes do nothing.

Prints nothing and always exits 0: Codex treats exit 2 as a block on
Stop / UserPromptSubmit / PreToolUse and shows an error line for any other
non-zero code. Changing the registration in ``.codex/hooks.json`` requires
re-trusting it with ``/hooks``.
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

# macOS の通知ヘルパー（`notify-helper-mac codex` でビルドする .app の名前）
MAC_HELPER_NAME = "CodexNotify"
# 同期フック（Interrupt・SessionEnd）でヘルパーを打ち切る秒数
SYNC_REMOVE_TIMEOUT = 2.0

SOUND_ATTENTION = "Glass"
SOUND_DONE = "Hero"

QUESTION_TOOL = "request_user_input"
PLAN_MARKER = "<proposed_plan>"

REMOVE_EVENTS = ("UserPromptSubmit", "PostToolUse")
SYNC_REMOVE_EVENTS = ("Interrupt", "SessionEnd")


def _tool_input(payload: dict) -> dict:
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def _first_question(tool_input: dict) -> str:
    questions = tool_input.get("questions")
    if isinstance(questions, list) and questions and isinstance(questions[0], dict):
        for key in ("question", "header"):
            text = questions[0].get(key)
            if isinstance(text, str) and text:
                return text
    return "回答が必要です"


def _describe_tool(name: str, tool_input: dict) -> str:
    """承認理由、無ければ「ツール名: コマンド」、どちらも無ければツール名。"""
    description = tool_input.get("description")
    if isinstance(description, str) and description:
        return description
    command = tool_input.get("command")
    if isinstance(command, str) and command:
        return f"{name}: {command}"
    return name


def build_notification(payload: dict) -> tuple[str, str, str] | None:
    """イベントから `(label, body, sound)` を決める。通知しないイベントなら None。"""
    event = payload.get("hook_event_name") or ""
    if event == "PreToolUse":
        if payload.get("tool_name") == QUESTION_TOOL:
            return "❓ 質問", _first_question(_tool_input(payload)), SOUND_ATTENTION
        return None
    if event == "PermissionRequest":
        tool = str(payload.get("tool_name") or "")
        return "🔐 許可待ち", _describe_tool(tool, _tool_input(payload)), SOUND_ATTENTION
    if event == "Stop":
        message = str(payload.get("last_assistant_message") or "")
        # Plan モードのプランは専用ツールが無く、最後の応答に <proposed_plan> として入る
        if PLAN_MARKER in message:
            return "📋 プラン確認待ち", "プランを確認してください", SOUND_ATTENTION
        return "✅ 完了", message or "応答が完了しました", SOUND_DONE
    return None


def handle(payload: dict) -> dict:
    """1 イベントを処理し、結果を返す（テスト用）。"""
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
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return 0
    if isinstance(payload, dict):
        handle(payload)
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
