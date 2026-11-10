#!/usr/bin/env python3
"""UserPromptSubmit hook that translates the user's prompt to English.

Every time the user submits a prompt (this event fires once per turn,
before Claude processes anything), this hook sends the raw prompt text to
the `aim` CLI (tools/aim, OpenRouter-backed) and asks for an English
translation. The translation is attached via `additionalContext` --
UserPromptSubmit hooks cannot replace or rewrite the original prompt text
itself, only add context alongside it (see Claude Code hooks reference).
Claude therefore sees both the original prompt and the English translation,
and is instructed to treat the translation as the authoritative reading of
user intent.

The source language is never assumed. The translation prompt sent to `aim`
is written to auto-detect whatever language the input is in (Japanese,
English, or anything else) and always produce English output, so this hook
works regardless of what language the user types in.

Falls through silently (exits 0, no additionalContext added) whenever
translation isn't applicable or fails: empty prompt, the `aim` command not
being on PATH, or any CLI/timeout error (including a missing
OPENROUTER_API_KEY, which `aim` itself reports). This hook must never be
the reason a prompt fails to reach Claude.
"""

"""
以下を前提とする:
- `tools/aim` にある `aim CLI` インストール済
- OPENROUTER_API_KEY 環境変数設定済
"""

"""
環境変数（すべて省略可）:
- `AIM_TRANSLATE_MODEL`        `aim --model` に渡すモデルの略記（デフォルト: minimax-m3。
                               `aim --list-models` で選択肢を確認できる）
- `AIM_TRANSLATE_MAX_INPUT_CHARS` aimに送るプロンプト本文の上限文字数、超過分は末尾切り捨て
                               （デフォルト: 20000）
- `AIM_TRANSLATE_TIMEOUT`      `aim` 呼び出しのタイムアウト秒数（デフォルト: 45。
                               フック自体の`timeout`設定値より小さくすること）
- `HOOK_LOG`                   このフックの「デバッグログ」（詳細ログ）を配置先ディレクトリの`logs/translate_prompt/`
                               に書き出すかどうか（true/false等）。フック自体の有効/無効ではない
                               （そちらは登録の有無で決まる）。
                               未設定ならスクリプト先頭の`ENABLE_HOOK_LOG`に従う。
                               配置先ディレクトリの`.env`に設定されていればそちらが優先。
"""
import os
import shutil
import subprocess

from .common.aim_client import run_aim
from .common.runtime import env_int, init_hook_context

# Debug-log ON/OFF only (writes to logs/translate_prompt/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

DEFAULT_MAX_INPUT_CHARS = 20000
DEFAULT_TIMEOUT = 45
DEFAULT_MODEL = "minimax-m3"

SYSTEM_PROMPT = (
    "You are a translation assistant embedded in a coding tool. You will be "
    "given a prompt that a user submitted to an AI coding assistant. The "
    "prompt may be written in any language -- do not assume which one; "
    "detect it from the text itself. Translate it into natural, fluent "
    "English. If it is already entirely in English, output it unchanged. "
    "Preserve code snippets, file paths, identifiers, command names, and "
    "any text inside quotes or code fences exactly as-is -- do not "
    "translate those. Output ONLY the translated prompt text, with no "
    "preamble, explanation, or surrounding quotes."
)


def call_aim(model, prompt, max_input_chars, timeout):
    truncated = False
    if len(prompt) > max_input_chars:
        prompt = prompt[:max_input_chars]
        truncated = True

    user_prompt = prompt + ("\n\n[prompt truncated before translation]" if truncated else "")
    full_prompt = f"{SYSTEM_PROMPT}\n\n---\n{user_prompt}\n---"

    return run_aim(model, full_prompt, timeout)


def main():
    payload, log, finish = init_hook_context(SCRIPT_NAME, ENABLE_HOOK_LOG)

    log["hook_event_name"] = payload.get("hook_event_name")
    if payload.get("hook_event_name") != "UserPromptSubmit":
        finish(0, reason="not a UserPromptSubmit event")

    prompt = payload.get("prompt")
    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        finish(0, reason="empty prompt")

    if shutil.which("aim") is None:
        finish(0, reason="aim command not found on PATH")  # pass through untouched

    model = os.environ.get("AIM_TRANSLATE_MODEL", DEFAULT_MODEL)
    max_input_chars = env_int("AIM_TRANSLATE_MAX_INPUT_CHARS", DEFAULT_MAX_INPUT_CHARS)
    timeout = env_int("AIM_TRANSLATE_TIMEOUT", DEFAULT_TIMEOUT)
    log["model"] = model
    log["max_input_chars"] = max_input_chars
    log["timeout"] = timeout
    log["prompt_chars"] = len(prompt)

    try:
        translation = call_aim(model, prompt, max_input_chars, timeout)
    except (subprocess.TimeoutExpired, RuntimeError, OSError) as e:
        finish(0, reason="aim CLI failure", error=repr(e))

    log["translation"] = translation

    result = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "The user's prompt above may not be in English. Here is an "
                f"automated English translation (via aim/{model}) of that "
                "same prompt, provided so you can read the user's intent "
                "unambiguously. Treat it as the authoritative reading of "
                "what the user asked, but reply to the user in whatever "
                "language is otherwise appropriate for the conversation:\n\n"
                f"{translation}"
            ),
        }
    }
    finish(0, output=result, reason="translated", result=result)


if __name__ == "__main__":
    main()
