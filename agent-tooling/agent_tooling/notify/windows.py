"""Windows バックエンド: winsound／winreg の音と、tkinter のポップアップ。

インライン化でトップレベル名が平坦化されるため、ここの名前はすべて `_win_` で始める。
OS 依存の標準ライブラリ（winsound・winreg・tkinter）は関数内で import する。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _win_asterisk_sound_configured() -> bool:
    """Windows の「Asterisk（情報）」システムサウンドが実際に割り当てられているか。

    MessageBeep(MB_ICONASTERISK) は、サウンドスキームで Asterisk が「なし」に
    設定されていると音が出ないのに呼び出しは成功してしまう（戻り値では判別不可）。
    そこでレジストリ HKCU\\AppEvents\\Schemes\\Apps\\.Default\\SystemAsterisk\\.Current
    の値を確認し、空文字列＝「未割り当て」とみなして Beep トーン生成へ逃がす。
    キー不在（ユーザー設定未変更）はスキーム既定に頼るしかないので True 扱い。
    """
    try:
        import winreg
    except ImportError:  # 非 Windows 環境等
        return True  # 判定不能なら従来どおり MessageBeep を試す
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"AppEvents\Schemes\Apps\.Default\SystemAsterisk\.Current",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return bool(value and value.strip())
    except OSError:
        return True


def _win_play_beep_or_tone() -> dict:
    """システムAsterisk音が割り当てられていれば MessageBeep、無ければ Beep トーン生成。

    Beep(freq, dur) はシステムサウンド設定に依存せず PC のスピーカーから
    直接トーンを鳴らすため、スキーム「なし」でも確実に音が出る。
    MessageBeep が例外で失敗した場合も Beep トーンで逃がす。
    """
    import winsound

    if _win_asterisk_sound_configured():
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return {"ok": True, "mode": "beep", "path": None}
        except Exception as exc:
            try:
                winsound.Beep(880, 300)
                return {
                    "ok": True,
                    "mode": "tone_fallback",
                    "path": None,
                    "detail": str(exc),
                }
            except Exception as tone_exc:
                return {
                    "ok": False,
                    "mode": "beep_failed",
                    "detail": f"{exc}; {tone_exc}",
                }
    # システムサウンド未割り当て: 直接トーン生成
    try:
        winsound.Beep(880, 300)
        return {"ok": True, "mode": "tone", "path": None}
    except Exception as exc:
        return {"ok": False, "mode": "tone_failed", "detail": str(exc)}


def _win_play_sound(sound_path: Path | None) -> dict:
    """`sound_path`（WAV のみ）を再生し、無い・失敗したらビープ／トーンへ逃がす。"""
    try:
        import winsound
    except ImportError as exc:
        return {"ok": False, "mode": "import_error", "detail": str(exc)}

    if sound_path is not None:
        try:
            # SND_FILENAME: path を WAV として再生 / SND_SYNC: 再生完了まで待つ
            # （プロセス終了で音が途切れるのを防ぐ）
            winsound.PlaySound(
                str(sound_path),
                winsound.SND_FILENAME | winsound.SND_SYNC,
            )
            return {"ok": True, "mode": "file", "path": str(sound_path)}
        except Exception as exc:
            # ファイル破損等でもビープ/トーンへフォールバック
            result = _win_play_beep_or_tone()
            return {**result, "path": str(sound_path), "detail": str(exc)}

    return _win_play_beep_or_tone()


def _win_spawn_popup(
    text: str, seconds: float, project: str, entry_script: Path, popup_flag: str
) -> dict:
    """ポップアップを描く子プロセスをデタッチして起動し、すぐ戻る。

    tkinter の mainloop は自プロセスをブロックするため、フック本体の応答を待たせない
    よう別プロセスにする。インライン化後はこのモジュールのファイルが配置先に無いので、
    `__file__` ではなく呼び出し元のエントリ（`entry_script`）を再実行する。
    """
    # CREATE_NO_WINDOW: コンソールウィンドウを一切作らない。DETACHED_PROCESS
    # だけだと、Windows 11の既定ターミナル機構が新規コンソール要求を検知して
    # 新しいWindows Terminal（PowerShell）ウィンドウを前面に出してしまうため、
    # DETACHED_PROCESSではなくこちらを使う。
    # CREATE_NEW_PROCESS_GROUP: Ctrl+C 等のシグナルを親から引き継がない
    creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [
            sys.executable,
            str(Path(entry_script).resolve()),
            popup_flag,
            text,
            str(seconds),
            project,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )
    return {
        "ok": True,
        "mode": "spawned",
        "text": text,
        "seconds": seconds,
        "project": project,
    }


def _win_run_popup(text: str, seconds: float, project: str, app_name: str) -> None:
    """画面右下に最前面のポップアップを描く。クリックか時間切れで閉じる。"""
    import tkinter as tk

    root = tk.Tk()
    root.title(f"{app_name} - {project}")
    root.attributes("-topmost", True)
    try:
        root.attributes("-toolwindow", True)
    except tk.TclError:
        pass

    frame = tk.Frame(root, padx=24, pady=18)
    frame.pack()

    tk.Label(
        frame,
        text=project,
        font=("Segoe UI", 10, "bold"),
        justify="left",
        anchor="w",
    ).pack(fill="x")

    tk.Label(
        frame,
        text=text,
        font=("Segoe UI", 12),
        justify="left",
        anchor="w",
        wraplength=360,
    ).pack(fill="x", pady=(4, 0))

    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    margin = 24
    x = max(screen_width - width - margin, 0)
    y = max(screen_height - height - margin - 48, 0)  # タスクバー分を避ける
    root.geometry(f"{width}x{height}+{x}+{y}")

    # ユーザーが明示的にクリックしない限り、時間制限いっぱいまで表示し続ける
    # （Escape/Enter等のキー操作では閉じない）。
    root.bind("<Button-1>", lambda _event: root.destroy())
    root.after(max(int(seconds * 1000), 500), root.destroy)

    root.mainloop()
