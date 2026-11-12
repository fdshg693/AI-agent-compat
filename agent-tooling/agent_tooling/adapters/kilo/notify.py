#!/usr/bin/env python3
"""Kilo adapter for the ``notify`` scenario: posts a per-session notification
when Kilo needs the user, and removes it once the user responds.

Spawned by the sibling TypeScript plugin (``notify.ts``) once per relayed
event. The stdin JSON is ``{event, id, root, cwd, body, properties}``: ``id``
is the root session ID (the notification identifier), ``root`` says whether
the event's own session is the root, ``cwd`` is the root's directory, ``body``
is the last assistant reply (idle only) and ``properties`` are the event's
properties in the v2 SDK shape.

Post (title = ``<label> [<cwd folder>]``, subtitle = cwd with ``~``):

- ``session.status`` (idle, root only; the TS side drops other statuses):
  ✅ 完了 / ``body`` (「応答が完了しました」 when empty) / sound Hero
- ``permission.asked``: 🔐 許可待ち / ``permission patterns...``
  (「許可が必要です」 when empty) / sound Glass
- ``question.asked``: ❓ 質問 / the first question (its header when empty) /
  sound Glass

Remove: ``permission.replied``, ``question.replied``, ``question.rejected``;
``chat.message`` and ``session.deleted`` only for the root session (a child
``chat.message`` is a subagent being started).

Posting/removing needs the KiloNotify helper .app on macOS (``just --justfile
agent-compat/agent-tooling/justfile notify-helper-mac kilo``); without it posts
fall back to ``osascript`` and removes do nothing. Other OSes do nothing.

Prints nothing and always exits 0; the TS plugin ignores stdout. Copy both
agent_tooling/hooks/generated/kilo/notify.py and its .ts sidecar into
.kilo/plugin/.
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

# macOS の通知ヘルパー（`notify-helper-mac kilo` でビルドする .app の名前）
MAC_HELPER_NAME = "KiloNotify"

SOUND_ATTENTION = "Glass"
SOUND_DONE = "Hero"

REMOVE_EVENTS = ("permission.replied", "question.replied", "question.rejected")
ROOT_REMOVE_EVENTS = ("chat.message", "session.deleted")


def _properties(payload: dict) -> dict:
    value = payload.get("properties")
    return value if isinstance(value, dict) else {}


def _describe_permission(properties: dict) -> str:
    """「permission patterns...」（例: ``bash git push``）。"""
    words = [str(properties.get("permission") or "")]
    patterns = properties.get("patterns")
    if isinstance(patterns, list):
        words.extend(str(p) for p in patterns if isinstance(p, str))
    text = " ".join(words).strip()
    return text or "許可が必要です"


def _first_question(properties: dict) -> str:
    questions = properties.get("questions")
    if isinstance(questions, list) and questions and isinstance(questions[0], dict):
        for key in ("question", "header"):
            text = questions[0].get(key)
            if isinstance(text, str) and text:
                return text
    return "回答が必要です"


def build_notification(payload: dict) -> tuple[str, str, str] | None:
    """イベントから `(label, body, sound)` を決める。通知しないイベントなら None。"""
    event = payload.get("event") or ""
    if event == "session.status":
        if payload.get("root") is not True:
            return None
        body = str(payload.get("body") or "")
        if not body.strip():
            body = "応答が完了しました"
        return "✅ 完了", body, SOUND_DONE
    if event == "permission.asked":
        return "🔐 許可待ち", _describe_permission(_properties(payload)), SOUND_ATTENTION
    if event == "question.asked":
        return "❓ 質問", _first_question(_properties(payload)), SOUND_ATTENTION
    return None


def handle(payload: dict) -> dict:
    """1 イベントを処理し、結果を返す（テスト用）。"""
    event = payload.get("event") or ""
    session_id = str(payload.get("id") or "")
    if not session_id:
        return {"action": "none"}
    helper_app = mac_helper_app(MAC_HELPER_NAME)

    if event in REMOVE_EVENTS or (event in ROOT_REMOVE_EVENTS and payload.get("root") is True):
        return {"action": "remove", "result": notify_remove(session_id, helper_app=helper_app)}

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
