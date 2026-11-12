"""端末種別ごとの通知（音・視覚通知）。フック本体ではない。

各エージェントのアダプタ（例: `adapters/claude/stop_alert.py`）から呼ぶ共通処理。
`sys.platform` で下の表からバックエンドを選び、表に無い OS では
`{"ok": False, "mode": "unsupported"}` を返すだけにする。

約束事（詳細は同じディレクトリの AGENTS.md）:
- 環境変数・`.env`・`hook_dir()` を読まない。設定値は引数で受け取る
- 例外を外に出さない。stdout に書かない
- 結果は `ok`／`mode`（／`detail`）を持つ dict で返す（ログ・テスト用）
"""

from __future__ import annotations

import sys
from pathlib import Path

from .project import UNKNOWN_PROJECT_TITLE as UNKNOWN_PROJECT_TITLE
from .project import resolve_project_title as resolve_project_title
from .windows import _win_play_sound, _win_run_popup, _win_spawn_popup

# OS ごとのバックエンド。OS を足すときはモジュールを足してここに 1 行ずつ足す。
_SOUND_BACKENDS = {"win32": _win_play_sound}
_POPUP_SPAWNERS = {"win32": _win_spawn_popup}
_POPUP_WINDOWS = {"win32": _win_run_popup}


def _unsupported() -> dict:
    return {"ok": False, "mode": "unsupported", "detail": f"platform={sys.platform}"}


def notify_sound(sound_path: Path | None, *, enabled: bool = True) -> dict:
    """通知音を鳴らす。`sound_path` は再生するファイル（無ければ OS の既定音）。"""
    backend = _SOUND_BACKENDS.get(sys.platform)
    if backend is None:
        return _unsupported()
    if not enabled:
        return {"ok": False, "mode": "disabled"}
    try:
        return backend(sound_path)
    except Exception as exc:
        return {"ok": False, "mode": "error", "detail": str(exc)}


def notify_popup(
    text: str,
    seconds: float,
    project: str,
    *,
    entry_script: Path,
    popup_flag: str,
    enabled: bool = True,
) -> dict:
    """視覚通知を出す（呼び出し元をブロックしない）。

    Windows では `entry_script`（実行中のフック。インライン化後は `sys.argv[0]`）を
    `popup_flag text seconds project` 付きの別プロセスで再実行する。子プロセス側は
    呼び出し元のエントリが argv を分岐して `run_notify_popup()` を呼ぶ。
    """
    backend = _POPUP_SPAWNERS.get(sys.platform)
    if backend is None:
        return _unsupported()
    if not enabled:
        return {"ok": False, "mode": "disabled"}
    try:
        return backend(text, seconds, project, entry_script, popup_flag)
    except Exception as exc:
        return {"ok": False, "mode": "spawn_failed", "detail": str(exc)}


def run_notify_popup(text: str, seconds: float, project: str, app_name: str) -> None:
    """`notify_popup()` が起動した子プロセスの本体。ウィンドウを閉じるまで戻らない。"""
    backend = _POPUP_WINDOWS.get(sys.platform)
    if backend is not None:
        backend(text, seconds, project, app_name)
