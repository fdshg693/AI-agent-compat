#!/usr/bin/env python3
"""PostToolUse hook for the Read tool.

When a Read call returns a large text excerpt, this hook sends the content
to the `aim` CLI (tools/aim, OpenRouter-backed) for summarization and
replaces the tool result with the summary via `updatedToolOutput`, so the
raw text never lands in the main conversation context. The underlying file
read has already happened by the time this hook runs (PostToolUse can't
undo side effects) -- this only changes what Claude sees afterwards.

Falls through silently (exits 0, unchanged output) whenever summarization
isn't applicable or fails: missing/short content, non-text reads (images,
notebooks, PDFs), the `aim` command not being on PATH, or any CLI/timeout
error (including a missing OPENROUTER_API_KEY, which `aim` itself reports).
This hook must never be the reason a Read call appears to fail.
"""

"""
以下を前提とする:
- `tools/aim` にある `aim CLI` インストール済
- OPENROUTER_API_KEY 環境変数設定済
"""

"""
環境変数（すべて省略可）:
- `AIM_SUMMARY_MODEL`      `aim --model` に渡すモデルの略記（デフォルト: minimax-m3。
                           `aim --list-models` で選択肢を確認できる）
- `AIM_SUMMARY_THRESHOLD`  要約を発動する最小文字数（デフォルト: 4000）
- `AIM_SUMMARY_MAX_INPUT_CHARS` aimに送る本文の上限文字数、超過分は末尾切り捨て（デフォルト: 40000）
- `AIM_SUMMARY_TIMEOUT`    `aim` 呼び出しのタイムアウト秒数（デフォルト: 120）
- `HOOK_LOG`               このフックの「デバッグログ」（詳細ログ）を配置先ディレクトリの`logs/summarize_read/`
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

# Debug-log ON/OFF only (writes to logs/summarize_read/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

DEFAULT_THRESHOLD = 4000
DEFAULT_MAX_INPUT_CHARS = 40000
DEFAULT_TIMEOUT = 120
DEFAULT_MODEL = "minimax-m3"

SYSTEM_PROMPT = (
    "You are a summarization assistant embedded in a coding tool. You will "
    "be given an excerpt read from a file. Summarize it concisely so another "
    "AI coding assistant can use the summary as context instead of the full "
    "text. Preserve exact identifiers (function/class/variable names), "
    "signatures, important constants, and structural landmarks (section "
    "headings, line ranges they cover). Use bullet points. Do not omit "
    "details a coding assistant would need to answer questions about this "
    "content. If the excerpt is prose/documentation rather than code, "
    "summarize the key points and structure instead."
)


def call_aim(
    model, file_path, start_line, num_lines, total_lines, content, max_input_chars, timeout
):
    truncated = False
    if len(content) > max_input_chars:
        content = content[:max_input_chars]
        truncated = True

    user_prompt = (
        f"File: {file_path}\n"
        f"Lines {start_line}-{start_line + num_lines - 1} of {total_lines} total."
        + (" (excerpt truncated before summarization)" if truncated else "")
        + f"\n\n---\n{content}\n---\n\nSummarize the above."
    )
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    return run_aim(model, full_prompt, timeout)


def main():
    payload, log, finish = init_hook_context(SCRIPT_NAME, ENABLE_HOOK_LOG)

    log["tool_name"] = payload.get("tool_name")
    if payload.get("tool_name") != "Read":
        finish(0, reason="not a Read call")

    if shutil.which("aim") is None:
        finish(0, reason="aim command not found on PATH")  # pass through untouched

    tool_response = payload.get("tool_response") or {}
    log["tool_response_type"] = tool_response.get("type")
    if tool_response.get("type") != "text":
        finish(0, reason="non-text tool_response (image/pdf/notebook/etc.)")

    file_info = tool_response.get("file") or {}
    content = file_info.get("content")
    if not content:
        finish(0, reason="no content in file info")

    threshold = env_int("AIM_SUMMARY_THRESHOLD", DEFAULT_THRESHOLD)
    log["content_chars"] = len(content)
    log["threshold"] = threshold
    if len(content) < threshold:
        finish(0, reason="below threshold, no need to summarize")

    model = os.environ.get("AIM_SUMMARY_MODEL", DEFAULT_MODEL)
    max_input_chars = env_int("AIM_SUMMARY_MAX_INPUT_CHARS", DEFAULT_MAX_INPUT_CHARS)
    timeout = env_int("AIM_SUMMARY_TIMEOUT", DEFAULT_TIMEOUT)
    log["model"] = model
    log["max_input_chars"] = max_input_chars
    log["timeout"] = timeout

    file_path = file_info.get("filePath", "")
    start_line = file_info.get("startLine", 1)
    num_lines = file_info.get("numLines", 0)
    total_lines = file_info.get("totalLines", num_lines)
    log["file_path"] = file_path
    log["start_line"] = start_line
    log["num_lines"] = num_lines
    log["total_lines"] = total_lines

    try:
        summary = call_aim(
            model,
            file_path,
            start_line,
            num_lines,
            total_lines,
            content,
            max_input_chars,
            timeout,
        )
    except (subprocess.TimeoutExpired, RuntimeError, OSError) as e:
        finish(0, reason="aim CLI failure", error=repr(e))

    log["summary"] = summary
    original_chars = len(content)
    summarized_content = (
        f"[aim summary ({model}) of lines {start_line}-"
        f"{start_line + num_lines - 1} of {total_lines} total, "
        f"{original_chars} chars original]\n\n{summary}"
    )

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"The content of {file_path} (lines {start_line}-"
                f"{start_line + num_lines - 1}) was large ({original_chars} "
                f"chars) and has been replaced with an aim-generated "
                f"summary below. Re-read a narrower offset/limit range on "
                f"the same file if exact text (e.g. precise line numbers or "
                f"verbatim code) is needed."
            ),
            "updatedToolOutput": {
                "type": "text",
                "file": {
                    "filePath": file_path,
                    "content": summarized_content,
                    "startLine": start_line,
                    "numLines": num_lines,
                    "totalLines": total_lines,
                },
            },
        }
    }
    finish(0, output=result, reason="summarized", result=result)


if __name__ == "__main__":
    main()
