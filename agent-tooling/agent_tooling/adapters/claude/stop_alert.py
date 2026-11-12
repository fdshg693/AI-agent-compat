#!/usr/bin/env python3
"""Stop hook that plays an alert sound and shows a popup window when Claude
finishes a turn.

On Windows, plays `alert.wav` next to the installed hook if present (or the
path in `STOP_ALERT_SOUND`); otherwise falls back to a system beep. Also
spawns a detached, auto-closing tkinter popup (bottom-right, always-on-top)
so a muted/misconfigured sound setup still surfaces a visible notification.
The popup runs in a child process that re-executes this same file with
`--popup`. Never blocks the stop (always exits 0). Honors `stop_hook_active`
to avoid Stop-hook re-entry loops even though this hook does not block.

手動確認（配置済みファイルに対して実行する）:
- `python stop_alert.py --sound` 音だけ鳴らして結果を表示する（0=成功、1=失敗）
- `python stop_alert.py --popup "テスト" 5 my-project` ポップアップをその場で表示する
"""

"""
環境変数（省略可）:
- `STOP_ALERT_SOUND`         再生する WAV の絶対／相対パス。未設定なら
                              配置先ディレクトリの `alert.wav` を探し、無ければシステムビープ。
- `STOP_ALERT_SOUND_ENABLED` 音そのものを鳴らすかどうか（true/false等）。未設定なら true。
                              false にするとポップアップ通知のみになる。
- `STOP_ALERT_POPUP`         ポップアップ通知を出すかどうか（true/false等）。未設定なら true。
- `STOP_ALERT_POPUP_SECONDS` ポップアップが自動で閉じるまでの秒数。未設定なら 300。
- `STOP_ALERT_POPUP_TEXT`    ポップアップに表示するメッセージ。未設定なら既定文言。
- `HOOK_LOG`                  このフックの「デバッグログ」を配置先ディレクトリの`logs/stop_alert/`
                              に書き出すかどうか（true/false等）。フック自体の有効/無効ではない
                              （そちらは登録の有無で決まる）。
                              未設定ならスクリプト先頭の`ENABLE_HOOK_LOG`に従う。
                              配置先ディレクトリの`.env`に設定されていればそちらが優先。
"""
import json
import os
import sys
from pathlib import Path

from agent_tooling.notify import (
    notify_popup,
    notify_sound,
    resolve_project_title,
    run_notify_popup,
)

from .common.hook_log import is_log_enabled, resolve_bool_flag
from .common.paths import hook_dir
from .common.runtime import configure_utf8_stdio, make_finish

# Debug-log ON/OFF only (writes to logs/stop_alert/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]


SOUND_FLAG = "--sound"
POPUP_FLAG = "--popup"
APP_NAME = "Claude Code"
DEFAULT_SOUND_NAME = "alert.wav"
DEFAULT_POPUP_TEXT = "Claude Codeの応答が完了しました"
DEFAULT_POPUP_SECONDS = 300.0


def resolve_sound_path() -> Path | None:
    """再生する WAV: `STOP_ALERT_SOUND` → 配置先の `alert.wav` → 無ければ None（既定音）。"""
    env_path = os.environ.get("STOP_ALERT_SOUND", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate

    default = hook_dir() / DEFAULT_SOUND_NAME
    if default.is_file():
        return default
    return None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _project_title() -> str:
    """`CLAUDE_PROJECT_DIR` → git → この配置ファイルから上の `.claude` → "unknown"。"""
    return resolve_project_title(
        os.environ.get("CLAUDE_PROJECT_DIR"), anchor=Path(__file__), marker=".claude"
    )


def play_alert() -> dict:
    """アラート音を鳴らす（`STOP_ALERT_SOUND_ENABLED`・`STOP_ALERT_SOUND` を解決して渡す）。"""
    return notify_sound(
        resolve_sound_path(), enabled=resolve_bool_flag("STOP_ALERT_SOUND_ENABLED", True)
    )


def show_popup(text: str | None = None, seconds: float | None = None) -> dict:
    """ポップアップを別プロセスで出す（`STOP_ALERT_POPUP*` を解決して渡す）。"""
    message = text or os.environ.get("STOP_ALERT_POPUP_TEXT", "").strip() or DEFAULT_POPUP_TEXT
    duration = (
        seconds
        if seconds is not None
        else _env_float("STOP_ALERT_POPUP_SECONDS", DEFAULT_POPUP_SECONDS)
    )
    return notify_popup(
        message,
        duration,
        _project_title(),
        # インライン化後は notify/ のファイルが無いので、実行中のこのフックを再実行させる
        entry_script=Path(sys.argv[0]),
        popup_flag=POPUP_FLAG,
        enabled=resolve_bool_flag("STOP_ALERT_POPUP", True),
    )


def run_popup_window(argv: list[str]) -> None:
    """`--popup` 付きで起動された子プロセスの本体。argv は `[text, seconds, project]`（省略可）。"""
    text = argv[0] if len(argv) > 0 else DEFAULT_POPUP_TEXT
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

    log_enabled = is_log_enabled(ENABLE_HOOK_LOG)
    log = {}
    finish = make_finish(SCRIPT_NAME, log, log_enabled)

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # stdin が空／壊れていても音だけは鳴らす（手動テストやパイプ漏れ対策）
        payload = {}
        log["stdin"] = "unparsable"

    # Stop フックが自分自身を再トリガーしている最中は何もしない（無限ループ回避）
    if payload.get("stop_hook_active"):
        finish(0, reason="stop_hook_active, skipped")

    sound_result = play_alert()
    popup_result = show_popup()
    finish(0, reason="played", sound=sound_result, popup=popup_result)


if __name__ == "__main__":
    main()
