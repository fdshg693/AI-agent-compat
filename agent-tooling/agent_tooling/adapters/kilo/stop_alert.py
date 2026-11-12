#!/usr/bin/env python3
"""Kilo plugin helper: alert sound + popup when a Kilo session finishes a turn.

Spawned by the sibling TypeScript plugin (``event`` hook) on ``session.idle``
of a top-level session. The JSON input carries ``session_id``, ``cwd`` (the
session directory) and ``event``. Plays ``alert.wav`` next to this file (or
``STOP_ALERT_SOUND``), else a system beep, and shows the same detached
tkinter popup as the Claude Code ``stop_alert`` hook, titled
``Kilo Code - <folder name of cwd>``. Windows only; elsewhere it does nothing.

Prints nothing and always exits 0. Copy both
agent_tooling/hooks/generated/kilo/stop_alert.py and its .ts sidecar into
.kilo/plugin/. Environment variables (also readable from ``.env`` next to this
file) are the same as the Claude hook: ``STOP_ALERT_SOUND``,
``STOP_ALERT_SOUND_ENABLED``, ``STOP_ALERT_POPUP``,
``STOP_ALERT_POPUP_SECONDS``, ``STOP_ALERT_POPUP_TEXT``, ``HOOK_LOG``.

手動確認（配置済みファイルに対して実行する）:
- `python stop_alert.py --sound` 音だけ鳴らして結果を表示する（0=成功、1=失敗）
- `python stop_alert.py --popup "テスト" 5 my-project "Kilo Code"` ポップアップをその場で表示する
"""

import json
import os
import sys
from pathlib import Path

from agent_tooling.adapters.claude.common.hook_log import is_log_enabled
from agent_tooling.adapters.claude.common.play_alert_sound import play_alert
from agent_tooling.adapters.claude.common.runtime import configure_utf8_stdio, make_finish
from agent_tooling.adapters.claude.common.show_alert_popup import (
    POPUP_FLAG,
    run_popup_window,
    show_popup,
)

# Debug-log ON/OFF only (writes to logs/stop_alert/ next to this file).
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

SOUND_FLAG = "--sound"
APP_NAME = "Kilo Code"
KILO_POPUP_TEXT = "Kilo Codeの応答が完了しました"


def _project_title(payload):
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    if isinstance(cwd, str) and cwd.strip():
        name = Path(cwd.strip()).name
        if name:
            return name
    return None  # show_popup falls back to git / cwd resolution


def main():
    if sys.argv[1:2] == [POPUP_FLAG]:
        run_popup_window(sys.argv[2:])
        return
    if sys.argv[1:2] == [SOUND_FLAG]:
        result = play_alert()
        print(result)
        sys.exit(0 if result.get("ok") else 1)

    configure_utf8_stdio()
    log = {}
    finish = make_finish(SCRIPT_NAME, log, is_log_enabled(ENABLE_HOOK_LOG))

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
        log["stdin"] = "unparsable"
    if not isinstance(payload, dict):
        payload = {}
    log["session_id"] = payload.get("session_id")

    try:
        sound_result = play_alert()
        text = os.environ.get("STOP_ALERT_POPUP_TEXT", "").strip() or KILO_POPUP_TEXT
        popup_result = show_popup(
            text=text, project_title=_project_title(payload), app_name=APP_NAME
        )
    except Exception as exc:  # never fail the Kilo session
        finish(0, reason="error", detail=str(exc))
    finish(0, reason="played", sound=sound_result, popup=popup_result)


if __name__ == "__main__":
    main()
