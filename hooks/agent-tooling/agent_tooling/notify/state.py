"""通知の抑止状態（スヌーズ・消音）の読み書きと判定。OS 非依存。

状態ファイルは `<state_dir>/state.json` の 1 つ。形:

    {"version": 1,
     "global": {"snooze_until": <epoch 秒>, "mute_until": <epoch 秒>},
     "sessions": {"<session_id>": {同じ形}}}

- スヌーズ（`snooze`）: 期限まで音も窓も出さない。消音（`mute`）: 期限まで音だけ止める
- 値は期限付きのものだけを持つ。解除＝値を消す、期限切れ＝無視（書き込み時に掃除する）
- 読めない・壊れたファイルは「抑止なし」として扱う（壊れたときに通知が止まり続けないように）
- 書き込みは一時ファイル + `os.replace`（複数の窓が同時に書いても壊れたファイルを残さない）

インライン化でトップレベル名が平坦化されるため、ここの名前はすべて `_state_` で始める。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

_STATE_VERSION = 1
_STATE_FILE_NAME = "state.json"
_STATE_KINDS = ("snooze", "mute")
_STATE_SCOPES = ("global", "session")
# セッションの抑止の上限。stop_alert は SessionEnd で消せないので、期限で溜まらないようにする
_STATE_SESSION_MAX_SECONDS = 12 * 60 * 60


def _state_file(state_dir: Path) -> Path:
    return Path(state_dir) / _STATE_FILE_NAME


def _state_empty() -> dict:
    return {"version": _STATE_VERSION, "global": {}, "sessions": {}}


def _state_clean_entry(raw: object) -> dict:
    """`{"<kind>_until": 数値}` だけを残す。形が違うものは捨てる。"""
    if not isinstance(raw, dict):
        return {}
    entry = {}
    for kind in _STATE_KINDS:
        value = raw.get(f"{kind}_until")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            entry[f"{kind}_until"] = float(value)
    return entry


def _state_read(state_dir: Path | None) -> dict:
    """状態を読む。無い・読めない・壊れている・版が違うなら空の状態を返す。"""
    if state_dir is None:
        return _state_empty()
    try:
        raw = json.loads(_state_file(state_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _state_empty()
    if not isinstance(raw, dict) or raw.get("version") != _STATE_VERSION:
        return _state_empty()
    sessions = raw.get("sessions")
    return {
        "version": _STATE_VERSION,
        "global": _state_clean_entry(raw.get("global")),
        "sessions": {
            str(sid): _state_clean_entry(entry)
            for sid, entry in (sessions.items() if isinstance(sessions, dict) else ())
        },
    }


def _state_prune(data: dict, now: float) -> dict:
    """期限切れの値と、空になったセッションを消す。"""

    def alive(entry: dict) -> dict:
        return {key: until for key, until in entry.items() if until > now}

    sessions = {sid: alive(entry) for sid, entry in data["sessions"].items()}
    return {
        "version": _STATE_VERSION,
        "global": alive(data["global"]),
        "sessions": {sid: entry for sid, entry in sessions.items() if entry},
    }


def _state_write(state_dir: Path, data: dict) -> Path:
    path = _state_file(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _state_check(state_dir: Path | None, session_id: str, now: float | None = None) -> dict:
    """今効いている抑止。`{"snooze": {"scope", "until"} | None, "mute": 同じ}`。

    グローバルとセッションの両方が効いているときは、期限の遅い方を返す。
    """
    now = time.time() if now is None else now
    data = _state_read(state_dir)
    entries = [("global", data["global"])]
    if session_id:
        entries.append(("session", data["sessions"].get(session_id, {})))
    result: dict = {kind: None for kind in _STATE_KINDS}
    for kind in _STATE_KINDS:
        for scope, entry in entries:
            until = entry.get(f"{kind}_until")
            if until is None or until <= now:
                continue
            if result[kind] is None or until > result[kind]["until"]:
                result[kind] = {"scope": scope, "until": until}
    return result


def _state_set(
    state_dir: Path,
    kind: str,
    scope: str,
    until: float,
    *,
    session_id: str = "",
    now: float | None = None,
) -> Path:
    """抑止を書き込む（同じ範囲・種類の値は置き換え）。セッションの期限は 12 時間までに丸める。"""
    if kind not in _STATE_KINDS:
        raise ValueError(f"unknown kind: {kind}")
    if scope not in _STATE_SCOPES:
        raise ValueError(f"unknown scope: {scope}")
    if scope == "session" and not session_id:
        raise ValueError("session scope needs session_id")
    now = time.time() if now is None else now
    data = _state_read(state_dir)
    if scope == "global":
        entry = data["global"]
    else:
        until = min(until, now + _STATE_SESSION_MAX_SECONDS)
        entry = data["sessions"].setdefault(session_id, {})
    entry[f"{kind}_until"] = float(until)
    return _state_write(state_dir, _state_prune(data, now))


def _state_clear(
    state_dir: Path,
    *,
    session_id: str = "",
    kinds: tuple[str, ...] = _STATE_KINDS,
    now: float | None = None,
) -> Path:
    """`kinds` の抑止をグローバルと `session_id` のセッションの両方から消す。"""
    now = time.time() if now is None else now
    data = _state_read(state_dir)
    targets = [data["global"]]
    if session_id and session_id in data["sessions"]:
        targets.append(data["sessions"][session_id])
    for entry in targets:
        for kind in kinds:
            entry.pop(f"{kind}_until", None)
    return _state_write(state_dir, _state_prune(data, now))


def _state_end_of_today(now: float | None = None) -> float:
    """ローカル時刻で今日が終わる時刻（翌日 0:00）の epoch 秒。"""
    now = time.time() if now is None else now
    tm = time.localtime(now)
    # mktime は日の繰り上がりと夏時間を正規化する
    return time.mktime((tm.tm_year, tm.tm_mon, tm.tm_mday + 1, 0, 0, 0, 0, 0, -1))
