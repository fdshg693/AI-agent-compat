#!/usr/bin/env python3
"""Single script registered for both `PostToolUse` and `PostToolUseFailure`
(two `registrations` in `scenarios/long_run_collector/hook.yaml`); all actual
logic lives in `common/long_run_state.py`. Which event fired is read from
`hook_event_name` in the payload: `"PostToolUseFailure"` means the call
failed, anything else (including a missing field, this hook's fail-open
policy) is treated as success.

Every tool call is appended to this session's collection log
(`state/long_run/<timestamp>-<session_id>.jsonl`) and folded into two
per-session counters (see `common/long_run_state.py` for the actual policy):

- `weighted_count`: +1 per success, +3 per failure. `AskUserQuestion`
  resets it to zero instead of adding to it -- the counter tracks "weighted
  operations since the agent last checked in with the user". Reaching
  `LONG_RUN_OP_THRESHOLD` (default 30) resets it to zero and nudges.
- `failure_streak`: consecutive tool-call failures; any success (or
  `AskUserQuestion`) resets it to zero. Reaching
  `LONG_RUN_FAILURE_STREAK_THRESHOLD` (default 3) resets it to zero and
  nudges -- this is the signal for "stuck retrying the same failing command
  in a loop", which `weighted_count` alone would also eventually catch, but
  only much later.

Both thresholds can trigger on the same call; when they do, both nudge
messages are concatenated into one `reason` (see
`common.long_run_state.nudge_message()`). `PostToolUse`/`PostToolUseFailure`
can't undo the tool call that already ran, but `decision: "block"` still
delivers the `reason` text to Claude as feedback it can act on -- that's the
whole mechanism here, not an attempt to revert anything.

Never fails closed: missing `tool_name`/`session_id` just skips recording.
"""

"""
環境変数（省略可）:
- `LONG_RUN_OP_THRESHOLD` 加重操作量（成功+1・失敗+3）がAskUserQuestionなしで
                          いくつに達したらナッジを送るか（デフォルト: 30）。
- `LONG_RUN_FAILURE_STREAK_THRESHOLD` ツール呼び出しの失敗が連続何回続いたら
                          ナッジを送るか（デフォルト: 3）。
- `HOOK_LOG` このフックの「デバッグログ」を配置先ディレクトリの`logs/long_run_collector/`に
             書き出すかどうか（true/false等）。フック自体の有効/無効ではない
             （そちらは登録の有無で決まる）。
             未設定ならスクリプト先頭の`ENABLE_HOOK_LOG`に従う。
             配置先ディレクトリの`.env`に設定されていればそちらが優先。
"""
import os

from .common.long_run_state import record_and_maybe_nudge
from .common.paths import hook_dir
from .common.runtime import env_int, init_hook_context

# Debug-log ON/OFF only (writes to logs/long_run_collector/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
DEFAULT_WEIGHTED_THRESHOLD = 30
DEFAULT_FAILURE_STREAK_THRESHOLD = 3


def main():
    payload, log, finish = init_hook_context(SCRIPT_NAME, ENABLE_HOOK_LOG)

    tool_name = payload.get("tool_name")
    session_id = payload.get("session_id")
    log["tool_name"] = tool_name
    if not tool_name or not session_id:
        finish(0, reason="no tool_name/session_id in payload")

    success = payload.get("hook_event_name") != "PostToolUseFailure"
    log["success"] = success

    weighted_threshold = env_int("LONG_RUN_OP_THRESHOLD", DEFAULT_WEIGHTED_THRESHOLD)
    failure_streak_threshold = env_int(
        "LONG_RUN_FAILURE_STREAK_THRESHOLD", DEFAULT_FAILURE_STREAK_THRESHOLD
    )
    tool_input = payload.get("tool_input") or {}

    weighted_count, failure_streak, nudge = record_and_maybe_nudge(
        hook_dir(),
        session_id,
        tool_name,
        tool_input,
        success=success,
        weighted_threshold=weighted_threshold,
        failure_streak_threshold=failure_streak_threshold,
    )
    log["weighted_count"] = weighted_count
    log["failure_streak"] = failure_streak

    if nudge is None:
        finish(0, reason="recorded")

    output = {"decision": "block", "reason": nudge}
    finish(0, output=output, reason="threshold reached, nudge sent")


if __name__ == "__main__":
    main()
