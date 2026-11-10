#!/usr/bin/env python3
"""PreToolUse hook for the Read tool.

Blocks reads that would return >= CHAR_THRESHOLD characters and tells
Claude to delegate the read to a subagent instead, so the huge content
never lands in the main context window.
"""

"""
環境変数（省略可）:
- `HOOK_LOG` このフックの「デバッグログ」（詳細ログ）を配置先ディレクトリの`logs/block_large_read/`に
             書き出すかどうか（true/false等）。フック自体の有効/無効ではない
             （そちらは登録の有無で決まる）。
             未設定ならスクリプト先頭の`ENABLE_HOOK_LOG`に従う。
             配置先ディレクトリの`.env`に設定されていればそちらが優先。
"""
import os
import sys

from .common.runtime import init_hook_context

# Debug-log ON/OFF only (writes to logs/block_large_read/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

CHAR_THRESHOLD = 2000
DEFAULT_LIMIT = 2000  # matches the Read tool's own default page size (lines)


def main():
    payload, log, finish = init_hook_context(SCRIPT_NAME, ENABLE_HOOK_LOG)

    log["tool_name"] = payload.get("tool_name")
    if payload.get("tool_name") != "Read":
        finish(0, reason="not a Read call")

    tool_input = payload.get("tool_input") or {}
    log["tool_input"] = tool_input
    file_path = tool_input.get("file_path")
    if not file_path:
        finish(0, reason="no file_path in tool_input")

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        finish(0, reason="OSError opening file", error=str(e))
    except Exception as e:
        finish(0, reason="unexpected error opening file", error=str(e))

    offset = tool_input.get("offset") or 0
    start = max(offset - 1, 0) if offset > 0 else 0
    limit = tool_input.get("limit") or DEFAULT_LIMIT
    selected = lines[start : start + limit]
    char_count = sum(len(line) for line in selected)
    log["char_count"] = char_count
    log["char_threshold"] = CHAR_THRESHOLD

    if char_count < CHAR_THRESHOLD:
        finish(0, reason="below threshold, passed through")

    message = (
        f"このファイル({file_path})の読み取り内容は{char_count}文字あり、"
        f"巨大な読み取り内容です。メインの会話コンテキストを圧迫するため、"
        f"直接Readするのではなく、サブエージェント(Agent tool)に読ませて"
        f"要約・該当箇所の抽出をさせてください。"
    )
    print(message, file=sys.stderr)
    finish(2, reason="blocked: over threshold", message=message)


if __name__ == "__main__":
    main()
