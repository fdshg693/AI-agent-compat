#!/usr/bin/env python3
"""UserPromptExpansion hook for the task-tracker skill.

Extracts the task name from `command_args`, creates
`.claude/tasks/{task_name}/` under the project root if needed, and appends the current
`session_id` to that directory's `sessions.md`. Never blocks the expansion:
an invalid/missing task name is reported via `additionalContext` only, so
Claude (and the user) notice without the command failing outright.
"""

"""
環境変数（省略可）:
- `HOOK_LOG` このフックの「デバッグログ」（詳細ログ）を配置先ディレクトリの`logs/task_tracker_session/`に
             書き出すかどうか（true/false等）。フック自体の有効/無効ではない
             （そちらは登録の有無で決まる）。
             未設定ならスクリプト先頭の`ENABLE_HOOK_LOG`に従う。
             配置先ディレクトリの`.env`に設定されていればそちらが優先。
"""
import json
import os
import re
import sys
from datetime import datetime

from .common.hook_log import is_log_enabled, write_log
from .common.paths import resolve_project_dir
from .common.runtime import configure_utf8_stdio, read_json_stdin

# Debug-log ON/OFF only (writes to logs/task_tracker_session/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

# SKILL.md must apply the same rule when validating $0 itself.
TASK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def main():
    configure_utf8_stdio()

    log_enabled = is_log_enabled(ENABLE_HOOK_LOG)
    log = {}

    def finish(code, additional_context=None, **extra):
        log.update(extra)
        log["exit_code"] = code
        if log_enabled:
            write_log(SCRIPT_NAME, log)
        if additional_context:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptExpansion",
                            "additionalContext": additional_context,
                        }
                    },
                    ensure_ascii=False,
                )
            )
        sys.exit(code)

    payload = read_json_stdin(finish)

    log["command_name"] = payload.get("command_name")
    log["expansion_type"] = payload.get("expansion_type")

    # Defense in depth: don't rely solely on hook.yaml's `matcher`
    # to scope this to /task-tracker. Hyphenated matchers were historically
    # evaluated as unanchored regex on some Claude Code versions (see
    # writing-hooks/hooks.md's matcher pitfalls) and could match unrelated
    # command names; re-check explicitly regardless of what the harness did.
    if payload.get("command_name") != "task-tracker":
        finish(0, reason="command_name is not task-tracker")

    if payload.get("expansion_type") != "slash_command":
        finish(0, reason="not a slash_command expansion")

    command_args = (payload.get("command_args") or "").strip()
    task_name = command_args.split()[0] if command_args else ""
    log["task_name"] = task_name

    if not task_name or not TASK_NAME_RE.match(task_name):
        warning = (
            f"[task-tracker] タスク名 '{task_name}' が不正か空です"
            "（英数字・ハイフン・アンダースコアのみ、先頭は英数字である必要があります）。"
            "セッションIDの記録はスキップされました。ユーザーに正しいタスク名での再実行を促してください。"
        )
        finish(0, additional_context=warning, reason="invalid task name")

    session_id = payload.get("session_id")
    if not session_id:
        finish(0, reason="no session_id in payload")

    project_dir = resolve_project_dir(payload)
    task_dir = os.path.join(project_dir, ".claude", "tasks", task_name)
    os.makedirs(task_dir, exist_ok=True)

    sessions_path = os.path.join(task_dir, "sessions.md")
    is_new = not os.path.exists(sessions_path)

    last_session_id = None
    if not is_new:
        with open(sessions_path, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f if line.strip()]
        if lines:
            parts = lines[-1].rsplit(" ", 1)
            if len(parts) == 2:
                last_session_id = parts[1]

    if last_session_id == session_id:
        finish(0, reason="duplicate session_id, not appended", task_dir=task_dir)

    timestamp = datetime.now().astimezone().isoformat()
    with open(sessions_path, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# task-tracker sessions: {task_name}\n\n")
        f.write(f"- {timestamp} {session_id}\n")

    finish(0, reason="session recorded", task_dir=task_dir, session_id=session_id)


if __name__ == "__main__":
    main()
