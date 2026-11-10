#!/usr/bin/env python3
"""Stop hook that records "what Claude said to the user" into the same
collection log `long_run_collector.py` (registered for both `PostToolUse`
and `PostToolUseFailure`) writes tool calls to
(`state/long_run/<timestamp>-<session_id>.jsonl`, `type: "statement"`).

There is no per-message hook event for assistant text (only `PreToolUse`/
`PostToolUse` fire per tool call), so this reads the session transcript
(`transcript_path` from the hook payload) instead, scanning only the lines
past `transcript_offset` (persisted in the shared state file) so repeated
Stop firings in the same session never re-log the same statement twice.

Never blocks the turn (always exits 0, regardless of outcome) and honors
`stop_hook_active` to avoid doing pointless re-work if Claude Code re-fires
this Stop hook for an unrelated reason (e.g. another Stop hook blocking).
This hook does not participate in the operation-count/nudge threshold at
all -- that's `common.long_run_state.record_and_maybe_nudge()`, driven only
by tool calls.
"""

"""
環境変数（省略可）:
- `HOOK_LOG` このフックの「デバッグログ」を配置先ディレクトリの`logs/long_run_statement_collector/`に
             書き出すかどうか（true/false等）。フック自体の有効/無効ではない
             （そちらは登録の有無で決まる）。
             未設定ならスクリプト先頭の`ENABLE_HOOK_LOG`に従う。
             配置先ディレクトリの`.env`に設定されていればそちらが優先。
"""
import json
import os

from .common.long_run_state import append_log, load_state, save_state, session_paths
from .common.paths import hook_dir
from .common.runtime import init_hook_context

# Debug-log ON/OFF only (writes to logs/long_run_statement_collector/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]


def extract_assistant_texts(transcript_path, start_line):
    """Return (texts, new_line_count) for assistant text blocks in lines
    `[start_line, end)` of the transcript jsonl. Unparsable/missing lines
    and non-text content are skipped, never raised -- a corrupt transcript
    should never break the Stop hook."""
    texts = []
    line_count = start_line
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for i, raw in enumerate(f):
                if i < start_line:
                    continue
                line_count = i + 1
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                content = (obj.get("message") or {}).get("content") or []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            texts.append(text)
    except OSError:
        return texts, start_line
    return texts, line_count


def main():
    payload, log, finish = init_hook_context(SCRIPT_NAME, ENABLE_HOOK_LOG)

    if payload.get("stop_hook_active"):
        finish(0, reason="stop_hook_active, skipping")

    session_id = payload.get("session_id")
    transcript_path = payload.get("transcript_path")
    log["session_id"] = session_id
    if not session_id or not transcript_path:
        finish(0, reason="missing session_id/transcript_path")

    state_file, log_file = session_paths(hook_dir(), session_id)

    state = load_state(state_file)
    texts, new_offset = extract_assistant_texts(transcript_path, state["transcript_offset"])

    for text in texts:
        append_log(log_file, {"type": "statement", "text": text})

    state["transcript_offset"] = new_offset
    save_state(state_file, state)

    finish(0, reason="recorded", statements=len(texts))


if __name__ == "__main__":
    main()
