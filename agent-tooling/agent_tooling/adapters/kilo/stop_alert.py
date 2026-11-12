#!/usr/bin/env python3
"""Kilo plugin helper: alert sound + visual notification when a Kilo session finishes a turn.

Spawned by the sibling TypeScript plugin (``event`` hook) on ``session.idle``
of a top-level session. The JSON input carries ``session_id``, ``cwd`` (the
session directory) and ``event``. Plays ``alert.wav`` next to this file (or
``STOP_ALERT_SOUND``), else the OS default sound, and shows the same visual
notification as the Claude Code ``stop_alert`` hook (``agent_tooling/notify/``):

- Windows: a detached tkinter popup titled ``Kilo Code - <folder name of cwd>``.
- macOS: a Notification Center notification keyed by ``session_id`` (via the
  KiloNotify helper .app when built, else ``osascript``).
- Other OSes: does nothing (``unsupported``).

Prints nothing and always exits 0. Copy both
agent_tooling/hooks/generated/kilo/stop_alert.py and its .ts sidecar into
.kilo/plugin/. Environment variables (also readable from ``.env`` next to this
file) are the same as the Claude hook: ``STOP_ALERT_SOUND``,
``STOP_ALERT_SOUND_ENABLED``, ``STOP_ALERT_POPUP``,
``STOP_ALERT_POPUP_SECONDS``, ``STOP_ALERT_POPUP_TEXT``, ``HOOK_LOG``.

手動確認（配置済みファイルに対して実行する）:
- `python stop_alert.py --sound` 音だけ鳴らして結果を表示する（0=成功、1=失敗）
- `python stop_alert.py --popup "テスト" 5 my-project` ポップアップをその場で表示する
"""

import json
import os
import sys
from pathlib import Path

from agent_tooling.adapters.claude.common.hook_log import is_log_enabled, resolve_bool_flag
from agent_tooling.adapters.claude.common.paths import hook_dir
from agent_tooling.adapters.claude.common.runtime import configure_utf8_stdio, make_finish
from agent_tooling.notify import (
    mac_helper_app,
    notify_popup,
    notify_sound,
    resolve_project_title,
    run_notify_popup,
    shorten_home,
)

# Debug-log ON/OFF only (writes to logs/stop_alert/ next to this file).
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

SOUND_FLAG = "--sound"
POPUP_FLAG = "--popup"
APP_NAME = "Kilo Code"
# macOS の通知ヘルパー（`notify-helper-mac kilo` でビルドする .app の名前）
MAC_HELPER_NAME = "KiloNotify"
DEFAULT_SOUND_NAME = "alert.wav"
KILO_POPUP_TEXT = "Kilo Codeの応答が完了しました"
DEFAULT_POPUP_SECONDS = 300.0


def resolve_sound_path() -> Path | None:
    """再生する WAV: `STOP_ALERT_SOUND` → 配置先の `alert.wav` → 無ければ None（既定音）。"""
    env_path = os.environ.get("STOP_ALERT_SOUND", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate
    default = hook_dir() / DEFAULT_SOUND_NAME
    return default if default.is_file() else None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _project_title(cwd: str = "") -> str:
    """セッションの `cwd` のフォルダ名 → git → この配置ファイルから上の `.kilo` → "unknown"。"""
    return resolve_project_title(cwd.strip() or None, anchor=Path(__file__), marker=".kilo")


def play_alert() -> dict:
    return notify_sound(
        resolve_sound_path(), enabled=resolve_bool_flag("STOP_ALERT_SOUND_ENABLED", True)
    )


def show_popup(*, session_id: str = "", cwd: str = "") -> dict:
    text = os.environ.get("STOP_ALERT_POPUP_TEXT", "").strip() or KILO_POPUP_TEXT
    return notify_popup(
        text,
        _env_float("STOP_ALERT_POPUP_SECONDS", DEFAULT_POPUP_SECONDS),
        _project_title(cwd),
        # インライン化後は notify/ のファイルが無いので、実行中のこのファイルを再実行させる
        entry_script=Path(sys.argv[0]),
        popup_flag=POPUP_FLAG,
        enabled=resolve_bool_flag("STOP_ALERT_POPUP", True),
        subtitle=shorten_home(cwd or os.getcwd()),
        notification_id=session_id,
        helper_app=mac_helper_app(MAC_HELPER_NAME),
    )


def run_popup_window(argv: list[str]) -> None:
    """`--popup` 付きで起動された子プロセスの本体。argv は `[text, seconds, project]`（省略可）。"""
    text = argv[0] if len(argv) > 0 else KILO_POPUP_TEXT
    seconds = float(argv[1]) if len(argv) > 1 else DEFAULT_POPUP_SECONDS
    project = argv[2] if len(argv) > 2 else _project_title()
    run_notify_popup(text, seconds, project, APP_NAME)


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
        popup_result = show_popup(
            session_id=str(payload.get("session_id") or ""), cwd=str(payload.get("cwd") or "")
        )
    except Exception as exc:  # never fail the Kilo session
        finish(0, reason="error", detail=str(exc))
    finish(0, reason="played", sound=sound_result, popup=popup_result)


if __name__ == "__main__":
    main()
