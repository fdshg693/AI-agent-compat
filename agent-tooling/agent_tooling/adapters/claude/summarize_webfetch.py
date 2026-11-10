#!/usr/bin/env python3
"""PostToolUse hook for the WebFetch tool.

When a WebFetch call returns a large `result` (WebFetch already runs the
page through a small model internally, but the response can still be huge
-- e.g. when the prompt asks for a verbatim extraction), this hook:

1. Saves the full, unmodified `result` text to a log file under
   `logs/webfetch_fulltext/` next to the installed hook.
2. Sends that text to the `aim` CLI (tools/aim, OpenRouter-backed) for
   a further summary.
3. Replaces the tool result with the summary (plus the log file path) via
   `updatedToolOutput`, so the raw text never lands in the main
   conversation context, while still letting Claude re-read the full text
   from disk if it turns out to be needed.

Falls through silently (exits 0, unchanged output) whenever summarization
isn't applicable or fails: missing/short result, the `aim` command not
being on PATH, or any CLI/timeout error (including a missing
OPENROUTER_API_KEY, which `aim` itself reports). This hook must never be
the reason a WebFetch call appears to fail.
"""

"""
以下を前提とする:
- `tools/aim` にある `aim CLI` インストール済
- OPENROUTER_API_KEY 環境変数設定済
"""

"""
環境変数（すべて省略可）:
- `AIM_WEBFETCH_SUMMARY_MODEL`      `aim --model` に渡すモデルの略記（デフォルト: minimax-m3。
                                    `aim --list-models` で選択肢を確認できる）
- `AIM_WEBFETCH_SUMMARY_THRESHOLD`  要約を発動する最小文字数（デフォルト: 4000）
- `AIM_WEBFETCH_SUMMARY_MAX_INPUT_CHARS` aimに送る本文の上限文字数、超過分は末尾切り捨て（デフォルト: 40000。
                                    全文ログには切り捨て前の内容をそのまま保存する）
- `AIM_WEBFETCH_SUMMARY_TIMEOUT`    `aim` 呼び出しのタイムアウト秒数（デフォルト: 120）
- `HOOK_LOG`                        このフックの「デバッグログ」（詳細ログ）を配置先ディレクトリの`logs/summarize_webfetch/`
                                    に書き出すかどうか（true/false等）。フック自体の有効/無効ではない
                                    （そちらは登録の有無で決まる）。
                                    未設定ならスクリプト先頭の`ENABLE_HOOK_LOG`に従う。
                                    配置先ディレクトリの`.env`に設定されていればそちらが優先。
                                    要約対象になった際の全文ログ（`webfetch_fulltext/`）は
                                    このフラグに関わらず常に書き出される。
"""
import os
import shutil
import subprocess
import time
import uuid

from .common.aim_client import run_aim
from .common.paths import hook_dir
from .common.runtime import env_int, init_hook_context

# Debug-log ON/OFF only (writes to logs/summarize_webfetch/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default. This is independent of the
# full-text result log under logs/webfetch_fulltext/, which is always written.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
FULLTEXT_DIR_NAME = "webfetch_fulltext"

DEFAULT_THRESHOLD = 4000
DEFAULT_MAX_INPUT_CHARS = 40000
DEFAULT_TIMEOUT = 120
DEFAULT_MODEL = "minimax-m3"

SYSTEM_PROMPT = (
    "You are a summarization assistant embedded in a coding tool. You will "
    "be given the result of fetching and processing a web page. Summarize "
    "it concisely so another AI coding assistant can use the summary as "
    "context instead of the full text. Preserve concrete facts, numbers, "
    "names, code snippets, and structural landmarks (headings, list items) "
    "that a coding assistant would need. Use bullet points. Do not omit "
    "details relevant to the original fetch prompt."
)


def write_fulltext_log(url, prompt, code, code_text, num_bytes, content):
    log_dir = os.path.join(hook_dir(), "logs", FULLTEXT_DIR_NAME)
    os.makedirs(log_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%dT%H%M%S", time.localtime())
    log_path = os.path.join(log_dir, f"{timestamp}-{uuid.uuid4().hex[:8]}.log")

    header = (
        f"URL: {url}\n"
        f"Prompt: {prompt}\n"
        f"HTTP: {code} {code_text}\n"
        f"Bytes fetched: {num_bytes}\n"
        f"Result chars: {len(content)}\n"
        f"---\n"
    )
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(content)

    return log_path


def call_aim(model, url, prompt, code, code_text, content, max_input_chars, timeout):
    truncated = False
    if len(content) > max_input_chars:
        content = content[:max_input_chars]
        truncated = True

    user_prompt = (
        f"URL: {url}\n"
        f"Original fetch prompt: {prompt}\n"
        f"HTTP status: {code} {code_text}\n"
        + (" (result truncated before summarization)" if truncated else "")
        + f"\n\n---\n{content}\n---\n\nSummarize the above."
    )
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    return run_aim(model, full_prompt, timeout)


def main():
    payload, log, finish = init_hook_context(SCRIPT_NAME, ENABLE_HOOK_LOG)

    log["tool_name"] = payload.get("tool_name")
    if payload.get("tool_name") != "WebFetch":
        finish(0, reason="not a WebFetch call")

    if shutil.which("aim") is None:
        finish(0, reason="aim command not found on PATH")  # pass through untouched

    tool_response = payload.get("tool_response") or {}
    if not isinstance(tool_response, dict):
        finish(0, reason="unexpected tool_response shape (not a dict)")

    content = tool_response.get("result")
    if not content or not isinstance(content, str):
        finish(0, reason="no result text in tool_response")

    threshold = env_int("AIM_WEBFETCH_SUMMARY_THRESHOLD", DEFAULT_THRESHOLD)
    log["content_chars"] = len(content)
    log["threshold"] = threshold
    if len(content) < threshold:
        finish(0, reason="below threshold, no need to summarize")

    tool_input = payload.get("tool_input") or {}
    url = tool_response.get("url") or tool_input.get("url", "")
    prompt = tool_input.get("prompt", "")
    code = tool_response.get("code")
    code_text = tool_response.get("codeText", "")
    num_bytes = tool_response.get("bytes")
    log["url"] = url

    try:
        log_path = write_fulltext_log(url, prompt, code, code_text, num_bytes, content)
    except OSError as e:
        finish(0, reason="failed to write full-text log", error=repr(e))
    log["fulltext_log_path"] = log_path

    model = os.environ.get("AIM_WEBFETCH_SUMMARY_MODEL", DEFAULT_MODEL)
    max_input_chars = env_int("AIM_WEBFETCH_SUMMARY_MAX_INPUT_CHARS", DEFAULT_MAX_INPUT_CHARS)
    timeout = env_int("AIM_WEBFETCH_SUMMARY_TIMEOUT", DEFAULT_TIMEOUT)
    log["model"] = model
    log["max_input_chars"] = max_input_chars
    log["timeout"] = timeout

    try:
        summary = call_aim(model, url, prompt, code, code_text, content, max_input_chars, timeout)
    except (subprocess.TimeoutExpired, RuntimeError, OSError) as e:
        finish(0, reason="aim CLI failure", error=repr(e))

    log["summary"] = summary
    original_chars = len(content)
    summarized_result = (
        f"[aim summary ({model}) of WebFetch result for {url} "
        f"({code} {code_text}), {original_chars} chars original]\n\n"
        f"{summary}\n\n"
        f"Full original result saved to: {log_path}"
    )

    updated_tool_response = dict(tool_response)
    updated_tool_response["result"] = summarized_result

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"The WebFetch result for {url} was large ({original_chars} "
                f"chars) and has been replaced with an aim-generated summary "
                f"below. The full original text was saved to {log_path} -- "
                f"read that file if exact/verbatim content is needed."
            ),
            "updatedToolOutput": updated_tool_response,
        }
    }
    finish(0, output=result, reason="summarized", result=result)


if __name__ == "__main__":
    main()
