"""Windows バックエンド: winsound／winreg の音と、tkinter のポップアップ。

インライン化でトップレベル名が平坦化されるため、ここの名前はすべて `_win_` で始める。
OS 依存の標準ライブラリ（winsound・winreg・tkinter・ctypes）は関数内で import する。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .state import (
    _STATE_SESSION_MAX_SECONDS,
    _state_check,
    _state_clear,
    _state_end_of_today,
    _state_set,
)


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
    text: str,
    seconds: float,
    project: str,
    entry_script: Path,
    popup_flag: str,
    *,
    session_id: str = "",
    state_dir: Path | None = None,
    **_mac_only: object,
) -> dict:
    """ポップアップを描く子プロセスをデタッチして起動し、すぐ戻る。

    `_mac_only`（`subtitle`・`notification_id`・`helper_app`）は macOS 用で、ここでは使わない。
    `session_id` と `state_dir` は子プロセスへ渡し、同じセッションの古い窓の置き換えに使う
    （どちらかが空なら置き換えない）。

    tkinter の mainloop は自プロセスをブロックするため、フック本体の応答を待たせない
    よう別プロセスにする。インライン化後はこのモジュールのファイルが配置先に無いので、
    `__file__` ではなく呼び出し元のエントリ（`entry_script`）を再実行する。
    argv は `popup_flag text seconds project session_id state_dir`（空は "" で渡す）。
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
            session_id,
            str(state_dir) if state_dir is not None else "",
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


# ---------------------------------------------------------------------------
# 同じセッションの古いポップアップの置き換え
# ---------------------------------------------------------------------------

_WIN_PROCESS_TERMINATE = 0x0001
_WIN_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _win_kernel32():
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.GetProcessTimes.restype = wintypes.BOOL
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k32.TerminateProcess.restype = wintypes.BOOL
    k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    return k32


def _win_process_started(pid: int) -> int | None:
    """プロセスの起動時刻（FILETIME の整数値）。開けない（終了済み等）なら None。

    pid は再利用されるので、pid と起動時刻の組でプロセスを特定する。
    """
    import ctypes
    from ctypes import wintypes

    k32 = _win_kernel32()
    handle = k32.OpenProcess(_WIN_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not k32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        created = times[0]
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        k32.CloseHandle(handle)


def _win_terminate(pid: int) -> bool:
    k32 = _win_kernel32()
    handle = k32.OpenProcess(_WIN_PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(k32.TerminateProcess(handle, 0))
    finally:
        k32.CloseHandle(handle)


def _win_popup_record_path(state_dir: Path, session_id: str) -> Path:
    """`<state_dir>/popup-<session_id>.json`。ファイル名に使えない文字は `_` にする。"""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", session_id)[:100]
    return Path(state_dir) / f"popup-{safe}.json"


def _win_read_popup_record(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    pid, started = data.get("pid"), data.get("started")
    if not isinstance(pid, int) or not isinstance(started, int):
        return None
    return {"pid": pid, "started": started}


def _win_replace_previous_popup(state_dir: Path | None, session_id: str) -> Path | None:
    """同じセッションの古いポップアップのプロセスを終了し、自分を記録する。

    記録（`pid` と `started`）と今のプロセスの起動時刻が一致するときだけ終了する
    （pid が再利用された無関係なプロセスを終了しない）。`session_id` か `state_dir` が
    空なら何もしない。失敗しても窓は出したいので例外は出さない。戻り値は記録したパス。
    """
    if not session_id or state_dir is None:
        return None
    path = _win_popup_record_path(state_dir, session_id)
    me = os.getpid()
    try:
        previous = _win_read_popup_record(path)
        if previous is not None and previous["pid"] != me:
            if _win_process_started(previous["pid"]) == previous["started"]:
                _win_terminate(previous["pid"])
        started = _win_process_started(me)
        if started is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{me}.tmp")
        tmp.write_text(json.dumps({"pid": me, "started": started}), encoding="utf-8")
        os.replace(tmp, path)
        return path
    except OSError:
        return None


def _win_forget_popup(path: Path | None) -> None:
    """窓を閉じたとき、記録がまだ自分を指していれば消す（新しい窓の記録は残す）。"""
    if path is None:
        return
    record = _win_read_popup_record(path)
    if record is None or record["pid"] != os.getpid():
        return
    try:
        path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# ポップアップの窓
# ---------------------------------------------------------------------------

_WIN_GWL_EXSTYLE = -20
_WIN_WS_EX_TOOLWINDOW = 0x00000080
_WIN_WS_EX_APPWINDOW = 0x00040000
_WIN_WS_EX_NOACTIVATE = 0x08000000
_WIN_SW_SHOWNOACTIVATE = 4
_WIN_SWP_NOSIZE = 0x0001
_WIN_SWP_NOMOVE = 0x0002
_WIN_SWP_NOZORDER = 0x0004
_WIN_SWP_NOACTIVATE = 0x0010
_WIN_SWP_FRAMECHANGED = 0x0020
_WIN_HWND_TOPMOST = -1
_WIN_LSFW_LOCK = 1
_WIN_LSFW_UNLOCK = 2


def _win_user32():
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.WinDLL("user32", use_last_error=True)
    u32.LockSetForegroundWindow.argtypes = [wintypes.UINT]
    u32.GetWindowLongW.restype = ctypes.c_long
    u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    u32.SetWindowLongW.restype = ctypes.c_long
    u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    u32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    return u32


def _win_set_app_id(app_name: str) -> None:
    """タスクバーで python.exe の他の窓とグループを分ける（失敗しても無視）。"""
    import ctypes

    app_id = "agent-tooling.notify." + re.sub(r"[^A-Za-z0-9]", "", app_name)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


def _win_run_popup(
    text: str,
    seconds: float,
    project: str,
    app_name: str,
    *,
    session_id: str = "",
    state_dir: Path | None = None,
) -> None:
    """画面右下に最前面のポップアップを描く。閉じるまで戻らない。

    タイトルバー付きの通常の窓（最小化でタスクバーに残る・リサイズ・最大化できる）。
    表示してもフォーカスを奪わない。× か「閉じる」で閉じ、`seconds` 経つと自動で閉じる
    （最小化したらタイマーを止め、復元しても再開しない）。同じ `session_id` の古い窓は
    終了してから出す。窓の例外は握りつぶさない（`--popup` を手で実行したときに見えるように）。
    """
    u32 = _win_user32()
    # Tk は外枠を作った瞬間に（非表示のまま）フォアグラウンドを取るので、Tk を作る前に
    # 前面化をロックする。ロックはシステム全体に効くので必ず解除する（二重の解除は無害）
    u32.LockSetForegroundWindow(_WIN_LSFW_LOCK)
    record = None
    try:
        record = _win_replace_previous_popup(state_dir, session_id)
        _win_set_app_id(app_name)
        _win_show_popup_window(
            u32, text, seconds, project, app_name, session_id=session_id, state_dir=state_dir
        )
    finally:
        u32.LockSetForegroundWindow(_WIN_LSFW_UNLOCK)
        _win_forget_popup(record)


def _win_format_remaining(seconds: float) -> str:
    """残り時間を「あと 1時間5分」「あと 12分」の形にする（1 分未満は切り上げ）。"""
    minutes = max(int((seconds + 59) // 60), 1)
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"あと {hours}時間{minutes}分"
    if hours:
        return f"あと {hours}時間"
    return f"あと {minutes}分"


def _win_suppression_text(state: dict, now: float) -> str:
    """`_state_check()` の結果を窓に出す 1 行にする。抑止が無ければ空文字。"""
    labels = {"snooze": "スヌーズ中", "mute": "消音中"}
    scopes = {"global": "すべて", "session": "このセッション"}
    parts = []
    for kind in ("snooze", "mute"):
        entry = state.get(kind)
        if entry:
            remaining = _win_format_remaining(entry["until"] - now)
            parts.append(f"{labels[kind]}（{scopes[entry['scope']]}・{remaining}）")
    return "　".join(parts)


# スヌーズの選択肢（ボタンの文言, 秒数）。スヌーズはすべてのセッションに効く
_WIN_SNOOZE_CHOICES = (("15分スヌーズ", 15 * 60), ("1時間スヌーズ", 60 * 60))


def _win_add_suppression_controls(
    root, actions, *, session_id: str, state_dir: Path | None
) -> None:
    """スヌーズ・消音のボタン列と、今の抑止を出す行を `actions` に足す。

    スヌーズを押したら状態を書いて窓を閉じる（「今は見ない」）。消音・解除は窓を残し、
    表示だけ更新する（「音だけ止めたい」）。`state_dir` が無ければ何も足さない
    （書き込み先が無い）。`session_id` が無ければ「このセッションを消音」は押せない。
    """
    import tkinter as tk

    if state_dir is None:
        return

    status = tk.Label(actions, text="", font=("Segoe UI", 9), fg="#555555", anchor="w")
    status.pack(side="top", fill="x", pady=(0, 6))
    snooze_row = tk.Frame(actions)
    snooze_row.pack(side="top", fill="x")
    mute_row = tk.Frame(actions)
    mute_row.pack(side="top", fill="x", pady=(6, 0))
    clear_button = tk.Button(mute_row, text="解除")

    def refresh() -> None:
        now = time.time()
        try:
            state = _state_check(state_dir, session_id, now)
        except Exception:
            state = {"snooze": None, "mute": None}
        status.configure(text=_win_suppression_text(state, now))
        if state["snooze"] or state["mute"]:
            clear_button.pack(side="right")
        else:
            clear_button.pack_forget()

    def write(action, *, close: bool = False) -> None:
        try:
            action(time.time())
        except (OSError, ValueError) as exc:
            status.configure(text=f"保存できませんでした: {exc}")
            return
        if close:
            root.destroy()
        else:
            refresh()

    for label, seconds in _WIN_SNOOZE_CHOICES:
        tk.Button(
            snooze_row,
            text=label,
            command=lambda s=seconds: write(
                lambda now: _state_set(state_dir, "snooze", "global", now + s, now=now),
                close=True,
            ),
        ).pack(side="left", padx=(0, 6))

    tk.Button(
        mute_row,
        text="このセッションを消音",
        state="normal" if session_id else "disabled",
        command=lambda: write(
            lambda now: _state_set(
                state_dir,
                "mute",
                "session",
                now + _STATE_SESSION_MAX_SECONDS,
                session_id=session_id,
                now=now,
            )
        ),
    ).pack(side="left", padx=(0, 6))
    tk.Button(
        mute_row,
        text="すべて消音（今日中）",
        command=lambda: write(
            lambda now: _state_set(state_dir, "mute", "global", _state_end_of_today(now), now=now)
        ),
    ).pack(side="left")
    clear_button.configure(
        command=lambda: write(lambda now: _state_clear(state_dir, session_id=session_id, now=now))
    )

    def tick() -> None:
        refresh()
        root.after(30_000, tick)

    tick()


def _win_show_popup_window(
    u32,
    text: str,
    seconds: float,
    project: str,
    app_name: str,
    *,
    session_id: str = "",
    state_dir: Path | None = None,
) -> None:
    """窓を作って mainloop を回す。呼び出し元が前面化をロックしている前提。

    `-toolwindow` などラッパー（外枠）を作り直す Tk 属性は使わない（取得した HWND が
    無効になる）。最前面も Tk の `-topmost` ではなく `SetWindowPos` で付ける。
    """
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    root.title(f"{app_name} - {project}")
    root.minsize(280, 140)

    # 下部の操作列は先に pack して、窓を縮めても隠れないようにする
    actions = tk.Frame(root, padx=12, pady=8)
    actions.pack(side="bottom", fill="x")
    close_row = tk.Frame(actions)
    close_row.pack(side="bottom", fill="x", pady=(6, 0))
    tk.Button(close_row, text="閉じる", width=8, command=root.destroy).pack(side="right")
    _win_add_suppression_controls(root, actions, session_id=session_id, state_dir=state_dir)

    body = tk.Frame(root, padx=24, pady=18)
    body.pack(side="top", fill="both", expand=True)
    tk.Label(
        body,
        text=project,
        font=("Segoe UI", 10, "bold"),
        justify="left",
        anchor="w",
    ).pack(fill="x")
    message = tk.Label(
        body,
        text=text,
        font=("Segoe UI", 12),
        justify="left",
        anchor="nw",
        wraplength=360,
    )
    message.pack(fill="both", expand=True, pady=(4, 0))
    # 本文の折り返し幅を窓幅に追従させる（左右の padx 分を引く）
    body.bind("<Configure>", lambda event: message.configure(wraplength=max(event.width - 48, 120)))

    # 外枠 HWND は withdraw 中の update_idletasks で作られる
    root.update_idletasks()
    hwnd = int(root.wm_frame(), 16)
    exstyle = u32.GetWindowLongW(hwnd, _WIN_GWL_EXSTYLE)
    # NOACTIVATE: クリックしてもアクティブにならない。APPWINDOW: これが無いとタスクバーから消える
    exstyle = (exstyle | _WIN_WS_EX_NOACTIVATE | _WIN_WS_EX_APPWINDOW) & ~_WIN_WS_EX_TOOLWINDOW
    u32.SetWindowLongW(hwnd, _WIN_GWL_EXSTYLE, exstyle)
    flags = _WIN_SWP_NOMOVE | _WIN_SWP_NOSIZE | _WIN_SWP_NOACTIVATE
    u32.SetWindowPos(hwnd, None, 0, 0, 0, 0, flags | _WIN_SWP_NOZORDER | _WIN_SWP_FRAMECHANGED)

    width = max(root.winfo_reqwidth(), 420)
    height = root.winfo_reqheight()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    margin = 24
    x = max(screen_width - width - margin, 0)
    # タスクバー（約 48px）とタイトルバー（約 32px）を避ける
    y = max(screen_height - height - margin - 48 - 32, 0)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.update_idletasks()

    # Win32 で表示してから Tk に状態を合わせる（deiconify しないと中身が描かれない）
    u32.ShowWindow(hwnd, _WIN_SW_SHOWNOACTIVATE)
    root.deiconify()
    u32.SetWindowPos(hwnd, _WIN_HWND_TOPMOST, 0, 0, 0, 0, flags)
    # Tk の遅れて来る前面化の要求をやり過ごしてからロックを解除する
    root.after(200, lambda: u32.LockSetForegroundWindow(_WIN_LSFW_UNLOCK))

    # 最小化は「後で見るので残す」という明示の操作なので、自動クローズを止める
    timer = {"id": root.after(max(int(seconds * 1000), 500), root.destroy)}

    def on_unmap(event) -> None:
        if event.widget is root and timer["id"] is not None and root.state() == "iconic":
            root.after_cancel(timer["id"])
            timer["id"] = None

    root.bind("<Unmap>", on_unmap)
    root.mainloop()
