"""Shared state/log helpers for the long-running-turn watchdog hook trio.

`long_run_collector.py` (registered for both `PostToolUse` and
`PostToolUseFailure`) calls `record_and_maybe_nudge()` for every tool call
in the session; `long_run_statement_collector.py` (Stop) calls
`append_log()` directly to record assistant statements. Both share one
per-session state file and one per-session collection log, named
`<timestamp>-<session_id>.json`/`.jsonl` (see `session_paths()`) so a plain
alphabetical directory listing sorts sessions chronologically instead of by
random session-id prefix:

- `state/long_run/<timestamp>-<session_id>.json` (next to the installed
  hooks, see `paths.hook_dir()`) -- small
  state: `weighted_count` (successes count 1, failures count
  `FAILURE_WEIGHT`, since the last `AskUserQuestion`), `failure_streak`
  (consecutive tool-call failures, reset by any success), and
  `transcript_offset` (how many transcript lines the Stop hook has already
  scanned for assistant text, so re-firing Stop mid-session never re-logs
  the same statement).
- `state/long_run/<timestamp>-<session_id>.jsonl` --
  append-only audit log of what was collected: one JSON object per line,
  `type` one of `read_file` / `command` / `tool_call` / `ask_user_question`
  / `statement`.

`<timestamp>` is minted once, the first time a session writes here
(`session_paths()`), and reused on every later call for that same
`session_id` -- a resumed session keeps appending to its original file
rather than starting a new one, found by globbing for an existing
`*-<session_id>.json` before minting a fresh timestamp.

`record_and_maybe_nudge()` is the one function with actual policy:
- Every tool call adds to `weighted_count` (`SUCCESS_WEIGHT` on success,
  `FAILURE_WEIGHT` on failure) except `AskUserQuestion`, which resets both
  counters to zero instead (the whole point of the watchdog is "operations
  since the agent last checked in with the user"). Once `weighted_count`
  reaches a threshold, it resets to zero and the caller nudges.
- Every failure increments `failure_streak`; any success resets it to zero.
  Once it reaches a (typically much lower) threshold, it resets to zero and
  the caller nudges -- this is what catches an agent stuck retrying the same
  failing command in a loop, which the weighted counter alone would also
  eventually catch, but only much later.
Both thresholds can trigger on the same call; the caller is expected to
combine both messages into one `reason`.

Must never raise on read: a missing/corrupt state or log file is treated as
"nothing recorded yet" so a bad file can never break the tool call or block
the turn this is attached to.
"""

import json
from datetime import datetime
from pathlib import Path

LONG_RUN_STATE_SUBDIR = ("state", "long_run")
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S"

SUCCESS_WEIGHT = 1
FAILURE_WEIGHT = 3


def _state_dir(hooks_dir):
    return Path(hooks_dir).joinpath(*LONG_RUN_STATE_SUBDIR)


def _find_existing_stem(state_dir, session_id):
    """Return this session's existing `<timestamp>-<session_id>` stem, if
    any file was already written for it, so a resumed session reuses its
    original timestamp instead of minting a new one. `None` for a session
    seen for the first time. Never raises -- a missing/unreadable state dir
    just means no existing file was found.
    """
    try:
        for path in state_dir.glob(f"*-{session_id}.json"):
            return path.stem
    except OSError:
        pass
    return None


def session_paths(hooks_dir, session_id):
    """Return `(state_file_path, log_file_path)` for this session, both
    built from one `<timestamp>-<session_id>` stem resolved exactly once so
    the two paths always agree -- callers needing both must use this instead
    of calling `state_path()`/`log_path()` separately, which would each
    independently mint a timestamp and could disagree.
    """
    state_dir = _state_dir(hooks_dir)
    stem = _find_existing_stem(state_dir, session_id)
    if stem is None:
        stem = f"{datetime.now().strftime(TIMESTAMP_FORMAT)}-{session_id}"
    return state_dir.joinpath(f"{stem}.json"), state_dir.joinpath(f"{stem}.jsonl")


def state_path(hooks_dir, session_id):
    return session_paths(hooks_dir, session_id)[0]


def log_path(hooks_dir, session_id):
    return session_paths(hooks_dir, session_id)[1]


def load_state(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    weighted_count = data.get("weighted_count")
    if not isinstance(weighted_count, int):
        weighted_count = 0
    failure_streak = data.get("failure_streak")
    if not isinstance(failure_streak, int):
        failure_streak = 0
    transcript_offset = data.get("transcript_offset")
    if not isinstance(transcript_offset, int):
        transcript_offset = 0
    return {
        "weighted_count": weighted_count,
        "failure_streak": failure_streak,
        "transcript_offset": transcript_offset,
    }


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_log(path, record):
    """Best-effort append of one JSON-line record. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = dict(record)
        record.setdefault("ts", datetime.now().astimezone().isoformat())
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str))
            f.write("\n")
    except Exception:
        pass


def build_log_entry(tool_name, tool_input, success):
    """Classify one tool call into a collection-log record.

    `Read` -> `read_file` (file path). `Bash`/`PowerShell` -> `command`
    (command text). `AskUserQuestion` -> `ask_user_question`. Everything
    else -> a generic `tool_call` so the log stays a complete operations
    trail even though only the first three types are broken out by name.
    """
    tool_input = tool_input or {}
    if tool_name == "Read":
        return {
            "type": "read_file",
            "tool": tool_name,
            "file_path": tool_input.get("file_path"),
            "success": success,
        }
    if tool_name in ("Bash", "PowerShell"):
        return {
            "type": "command",
            "tool": tool_name,
            "command": tool_input.get("command"),
            "success": success,
        }
    if tool_name == "AskUserQuestion":
        return {"type": "ask_user_question", "tool": tool_name, "success": success}
    return {"type": "tool_call", "tool": tool_name, "success": success}


def record_and_maybe_nudge(
    hooks_dir,
    session_id,
    tool_name,
    tool_input,
    success,
    weighted_threshold,
    failure_streak_threshold,
):
    """Append the collection-log entry for one tool call and update both
    counters.

    Returns `(weighted_count, failure_streak, nudge_message_or_None)`. The
    two int values are whatever triggered the decision (so callers can
    log/report them even when they were the reset-to-zero value from an
    `AskUserQuestion` call). Any counter that reached its threshold has
    already been reset to zero in storage -- the caller only needs to
    deliver the returned message to Claude.
    """
    state_file, log_file = session_paths(hooks_dir, session_id)

    append_log(log_file, build_log_entry(tool_name, tool_input, success))

    state = load_state(state_file)
    if tool_name == "AskUserQuestion":
        state["weighted_count"] = 0
        state["failure_streak"] = 0
        save_state(state_file, state)
        return 0, 0, None

    if success:
        state["weighted_count"] += SUCCESS_WEIGHT
        state["failure_streak"] = 0
    else:
        state["weighted_count"] += FAILURE_WEIGHT
        state["failure_streak"] += 1

    weighted_count = state["weighted_count"]
    failure_streak = state["failure_streak"]

    triggers = []
    if failure_streak >= failure_streak_threshold:
        triggers.append("failure_streak")
        state["failure_streak"] = 0
    if weighted_count >= weighted_threshold:
        triggers.append("weighted_threshold")
        state["weighted_count"] = 0

    save_state(state_file, state)

    if not triggers:
        return weighted_count, failure_streak, None

    message = nudge_message(
        triggers,
        failure_streak_threshold=failure_streak_threshold,
        weighted_threshold=weighted_threshold,
        failure_streak=failure_streak,
    )
    return weighted_count, failure_streak, message


def nudge_message(triggers, failure_streak_threshold, weighted_threshold, failure_streak):
    parts = []
    if "failure_streak" in triggers:
        parts.append(
            f"⚠️ ツール呼び出しの失敗が{failure_streak}回連続しました"
            f"（閾値{failure_streak_threshold}）。同じ失敗コマンドをリトライし続けるループに"
            "陥っていないか確認してください。\n"
            "1. ユーザーに状況を確認・質問すべきではないか（AskUserQuestionツールの使用を検討）\n"
            "2. コマンドの実行・結果取得自体をサブエージェント（Agentツール）に任せるべきではないか"
        )
    if "weighted_threshold" in triggers:
        parts.append(
            "⚠️ 直近のAskUserQuestion（ユーザーへの質問）以降の操作量"
            f"（成功+{SUCCESS_WEIGHT}・失敗+{FAILURE_WEIGHT}で加算）が閾値{weighted_threshold}"
            "に達しました。一度立ち止まり、次を自己点検してください。\n"
            "1. 状況は順調に進んでいるか（当初の目的からズレていないか）\n"
            "2. ユーザーに確認・質問すべき内容はないか（AskUserQuestionツールの使用を検討）\n"
            "3. 対応スコープを必要以上に広げていないか\n"
            "4. 定型作業や調査はサブエージェント（Agentツール）に任せるべきではないか"
        )
    parts.append(
        "上記を踏まえた上で、このまま作業を続けるか、ユーザーに確認するかを判断してください。"
    )
    return "\n\n".join(parts)
