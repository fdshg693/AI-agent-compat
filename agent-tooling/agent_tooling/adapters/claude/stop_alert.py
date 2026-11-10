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

from .common.hook_log import is_log_enabled
from .common.play_alert_sound import play_alert
from .common.runtime import configure_utf8_stdio, make_finish
from .common.show_alert_popup import POPUP_FLAG, run_popup_window, show_popup

# Debug-log ON/OFF only (writes to logs/stop_alert/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]


SOUND_FLAG = "--sound"


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
