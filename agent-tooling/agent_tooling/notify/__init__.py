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

from .macos import _mac_helper_app, _mac_play_sound, _mac_post, _mac_remove, _mac_spawn_popup
from .project import UNKNOWN_PROJECT_TITLE as UNKNOWN_PROJECT_TITLE
from .project import resolve_project_title as resolve_project_title
from .text import format_title as format_title
from .text import shorten_home as shorten_home
from .text import truncate_body as truncate_body
from .windows import _win_play_sound, _win_run_popup, _win_spawn_popup

# OS ごとのバックエンド。OS を足すときはモジュールを足してここに 1 行ずつ足す。
# `_SOUND_BACKENDS` と `_POPUP_SPAWNERS` の OS 集合は揃える。`_POPUP_WINDOWS` は
# 視覚通知を子プロセスで描く OS（Windows）だけが持つ。
_SOUND_BACKENDS = {"win32": _win_play_sound, "darwin": _mac_play_sound}
_POPUP_SPAWNERS = {"win32": _win_spawn_popup, "darwin": _mac_spawn_popup}
_POPUP_WINDOWS = {"win32": _win_run_popup}
# identifier 付きで出す・消す（同じ id の通知を置き換え・削除できる）。後から消せる仕組みを
# 持つ OS だけが持つ。Windows のポップアップは別プロセスで後から消せないので載せない。
# `_POST_BACKENDS` と `_REMOVE_BACKENDS` の OS 集合は揃える。
_POST_BACKENDS = {"darwin": _mac_post}
_REMOVE_BACKENDS = {"darwin": _mac_remove}


def _unsupported() -> dict:
    return {"ok": False, "mode": "unsupported", "detail": f"platform={sys.platform}"}


def notify_sound(sound_path: Path | None, *, enabled: bool = True) -> dict:
    """通知音を鳴らす。`sound_path` は再生するファイル（無ければ OS の既定音）。

    Windows は再生が終わるまで待つ（WAV のみ）。macOS は afplay を切り離して待たない。
    """
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
    subtitle: str = "",
    notification_id: str = "",
    helper_app: Path | None = None,
) -> dict:
    """視覚通知を出す（呼び出し元を長くブロックしない）。

    - Windows: `entry_script`（実行中のフック。インライン化後は `sys.argv[0]`）を
      `popup_flag text seconds project` 付きの別プロセスで再実行する。子プロセス側は
      呼び出し元のエントリが argv を分岐して `run_notify_popup()` を呼ぶ。
      `subtitle`・`notification_id`・`helper_app` は使わない
    - macOS: 通知センターへ同期で出す（タイトル=`project`、サブタイトル=`subtitle`、
      本文=`text` を整形したもの）。`notification_id` が同じ通知は置き換わる。
      `helper_app` は通知ヘルパー `<Name>.app`（`mac_helper_app()`）。`seconds` は使わない
    """
    backend = _POPUP_SPAWNERS.get(sys.platform)
    if backend is None:
        return _unsupported()
    if not enabled:
        return {"ok": False, "mode": "disabled"}
    try:
        return backend(
            text,
            seconds,
            project,
            entry_script,
            popup_flag,
            subtitle=subtitle,
            notification_id=notification_id,
            helper_app=helper_app,
        )
    except Exception as exc:
        return {"ok": False, "mode": "spawn_failed", "detail": str(exc)}


def run_notify_popup(text: str, seconds: float, project: str, app_name: str) -> None:
    """`notify_popup()` が起動した子プロセスの本体。ウィンドウを閉じるまで戻らない。"""
    backend = _POPUP_WINDOWS.get(sys.platform)
    if backend is not None:
        backend(text, seconds, project, app_name)


def notify_post(
    title: str,
    subtitle: str,
    body: str,
    *,
    sound: str = "",
    notification_id: str = "",
    helper_app: Path | None = None,
) -> dict:
    """identifier 付きの通知を出す（同期。上限付きで、呼び出し元を長くブロックしない）。

    `body` はここで整形する（`truncate_body()`）。`notification_id` が同じ通知は
    置き換わる（空なら置き換えの対象にしない）。`sound` は通知の音の名前（macOS は
    `Glass`・`Hero` などのシステムサウンド名。空なら音なし）。`helper_app` は通知ヘルパー
    `<Name>.app`（`mac_helper_app()`）。対応は macOS だけで、それ以外は `unsupported`。
    """
    backend = _POST_BACKENDS.get(sys.platform)
    if backend is None:
        return _unsupported()
    try:
        return backend(
            title,
            subtitle,
            truncate_body(body),
            sound=sound,
            notification_id=notification_id,
            helper_app=helper_app,
        )
    except Exception as exc:
        return {"ok": False, "mode": "error", "detail": str(exc)}


def notify_remove(
    notification_id: str,
    *,
    helper_app: Path | None = None,
    timeout: float | None = None,
) -> dict:
    """`notification_id` の通知を消す。`timeout` 秒（省略時は既定の上限）で打ち切る。

    id が空なら何もしない（`no_id`）。対応は macOS のヘルパー経由だけで、それ以外は
    `unsupported`。ヘルパーが無いと消せない（`helper_missing`）。
    """
    backend = _REMOVE_BACKENDS.get(sys.platform)
    if backend is None:
        return _unsupported()
    try:
        if timeout is None:
            return backend(notification_id, helper_app=helper_app)
        return backend(notification_id, helper_app=helper_app, timeout=timeout)
    except Exception as exc:
        return {"ok": False, "mode": "error", "detail": str(exc)}


def mac_helper_app(name: str) -> Path:
    """macOS の通知ヘルパー `<name>.app` の既定のパス（存在するとは限らない）。

    ビルドは `just --justfile agent-compat/agent-tooling/justfile notify-helper-mac`。
    """
    return _mac_helper_app(name)
