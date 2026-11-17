"""macOS バックエンド: 通知センターへの通知（Swift ヘルパー → osascript）と afplay の音。

インライン化でトップレベル名が平坦化されるため、ここの名前はすべて `_mac_` で始める。

- 通知: `helper_app`（`<Name>.app`。ソースは `macos_helper/`）があれば `post --id …` で出す。
  同じ id の通知は置き換わる。ヘルパーが無い・許可が未決定・その他のエラーなら osascript
  （値は argv で渡す）にフォールバックし、拒否されている（終了コード 3）なら何もしない。
  id が空ならヘルパーを使わず osascript で出す（id 無しでは置き換え・削除できないため）。
- 音: afplay でファイルを鳴らす。再生が終わるまで戻らないので、切り離して待たない。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .text import truncate_body

# ヘルパー・osascript の上限（秒）。どちらも通常 0.2 秒未満で終わる
_MAC_TIMEOUT_SECONDS = 6.0
# ヘルパーの終了コード（macos_helper/main.swift と合わせる）
_MAC_HELPER_EXIT_DENIED = 3
# 音のファイルが無いときに鳴らすシステムサウンド
_MAC_DEFAULT_SOUND = Path("/System/Library/Sounds/Glass.aiff")
# ヘルパー .app の既定の置き場所（`just … notify-helper-mac` のビルド先と合わせる）
_MAC_HELPER_DIR = Path("~/Library/Application Support/agent-tooling/notify")

# AppleScript には argv で値を渡し、文字列埋め込みによるエスケープ漏れを避ける
_MAC_OSASCRIPT = """on run argv
	display notification (item 3 of argv) with title (item 1 of argv) subtitle (item 2 of argv) sound name (item 4 of argv)
end run"""


def _mac_helper_app(name: str) -> Path:
    """ヘルパー `<name>.app` の既定のパス（存在するとは限らない）。"""
    return _MAC_HELPER_DIR.expanduser() / f"{name}.app"


def _mac_helper_bin(helper_app: Path | None) -> Path | None:
    """`.app` の中の実行ファイル。バンドル外へコピーすると動かないので中を直接 exec する。"""
    if helper_app is None:
        return None
    binary = Path(helper_app) / "Contents" / "MacOS" / Path(helper_app).stem
    return binary if binary.is_file() else None


def _mac_run_helper(helper_app: Path | None, args: list[str], timeout: float) -> dict:
    binary = _mac_helper_bin(helper_app)
    if binary is None:
        return {"ok": False, "mode": "helper_missing", "detail": str(helper_app)}
    try:
        result = subprocess.run(
            [str(binary), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "mode": "helper_timeout", "detail": f"{timeout}s"}
    except OSError as exc:
        return {"ok": False, "mode": "helper_error", "detail": str(exc)}
    if result.returncode == 0:
        return {"ok": True, "mode": "helper"}
    mode = "helper_denied" if result.returncode == _MAC_HELPER_EXIT_DENIED else "helper_failed"
    return {
        "ok": False,
        "mode": mode,
        "detail": f"exit={result.returncode}: {result.stderr.strip()}",
    }


def _mac_osascript(title: str, subtitle: str, body: str, sound: str) -> dict:
    try:
        result = subprocess.run(
            ["osascript", "-e", _MAC_OSASCRIPT, title, subtitle, body, sound],
            capture_output=True,
            text=True,
            timeout=_MAC_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "mode": "osascript_failed", "detail": str(exc)}
    if result.returncode != 0:
        return {
            "ok": False,
            "mode": "osascript_failed",
            "detail": f"exit={result.returncode}: {result.stderr.strip()}",
        }
    # osascript は通知が許可されていなくても 0 で終わるので、「出た」とは言い切れない
    return {"ok": True, "mode": "osascript"}


def _mac_post(
    title: str,
    subtitle: str,
    body: str,
    *,
    sound: str = "",
    notification_id: str = "",
    helper_app: Path | None = None,
) -> dict:
    """通知を出す。`body` は呼び出し側で整形済みのものを渡す。"""
    helper_result = None
    if notification_id:
        helper_result = _mac_run_helper(
            helper_app,
            [
                "post",
                "--id",
                notification_id,
                "--title",
                title,
                "--subtitle",
                subtitle,
                "--body",
                body,
                "--sound",
                sound,
            ],
            _MAC_TIMEOUT_SECONDS,
        )
        if helper_result["ok"]:
            return helper_result
        if helper_result["mode"] == "helper_denied":
            # ユーザーが通知を拒否している。osascript で出し直すと拒否を無視することになる
            return helper_result
    result = _mac_osascript(title, subtitle, body, sound)
    if helper_result is not None:
        result["helper"] = helper_result
    return result


def _mac_remove(
    notification_id: str,
    *,
    helper_app: Path | None = None,
    timeout: float = _MAC_TIMEOUT_SECONDS,
) -> dict:
    """`notification_id` の通知を消す。id が空・ヘルパーが無いなら何もしない。"""
    if not notification_id:
        return {"ok": False, "mode": "no_id"}
    return _mac_run_helper(helper_app, ["remove", "--id", notification_id], timeout)


def _mac_play_sound(sound_path: Path | None) -> dict:
    """`sound_path`（無ければ既定のシステムサウンド）を afplay で鳴らす。待たずに戻る。"""
    path = Path(sound_path) if sound_path is not None else _MAC_DEFAULT_SOUND
    subprocess.Popen(
        ["afplay", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return {"ok": True, "mode": "afplay", "path": str(path)}


def _mac_spawn_popup(
    text: str,
    seconds: float,
    project: str,
    entry_script: Path,
    popup_flag: str,
    *,
    subtitle: str = "",
    notification_id: str = "",
    helper_app: Path | None = None,
) -> dict:
    """視覚通知を通知センターへ出す（子プロセスは使わない。`seconds` は通知センターに任せる）。

    音は `notify_sound()` が別に鳴らすので、通知には音を付けない（二重に鳴らさない）。
    """
    del seconds, entry_script, popup_flag  # Windows のポップアップ用
    return _mac_post(
        project,
        subtitle,
        truncate_body(text),
        notification_id=notification_id,
        helper_app=helper_app,
    )
