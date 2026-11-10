#!/usr/bin/env python3
"""Stop hook that interviews Claude about auto-enquete-enabled skills it used
this session.

Reads the per-session state written by `skill_usage_tracker.py`
(`state/skill_usage/<session_id>.json`). For each tracked
skill, "already surveyed this session" is determined purely by whether
`<skill_dir>/enquete/<session_id>.md` exists yet -- no separate "surveyed"
flag is kept, so the check is self-healing even across partial/interrupted
writes.

If any tracked skill has no such file yet, this hook blocks the Stop
(exit 2) with a message telling Claude exactly which skills are pending,
where to Write each answer file, and what questions/template to fill in.
Blocking forces Claude to keep going instead of ending the turn; Claude
Code re-fires Stop hooks on the next stop attempt, so once Claude writes
the files this hook finds them and allows the turn to end.

This hook does not rely on `stop_hook_active` for its loop bound (unlike a
typical Stop hook, where checking it and bailing out early is the standard
guard against runaway re-entry -- see writing-hooks/hooks.md). Here the
natural termination condition is "all pending files exist", which
`stop_hook_active` can't express (both the first block and a later
still-pending block look the same). Instead a `stop_attempts` counter in
the state file caps this hook at `SKILL_ENQUETE_MAX_ATTEMPTS` (default 3)
blocks per session, independent of and well below Claude Code's own
8-block hard cap, so an uncooperative or distracted turn gives up quietly
(exit 0 + systemMessage) rather than exhausting that harness-wide cap.
"""

"""
環境変数（省略可）:
- `SKILL_ENQUETE_MAX_ATTEMPTS` このセッションで最大何回までStopをブロックしてアンケートを
                               促すか（デフォルト: 3）。超過すると残りは諦めて exit 0 する。
- `HOOK_LOG` このフックの「デバッグログ」を配置先ディレクトリの`logs/skill_enquete_stop/`に
             書き出すかどうか（true/false等）。フック自体の有効/無効ではない
             （そちらは登録の有無で決まる）。
             未設定ならスクリプト先頭の`ENABLE_HOOK_LOG`に従う。
             配置先ディレクトリの`.env`に設定されていればそちらが優先。
"""
import os
import sys
from datetime import datetime
from pathlib import Path

from .common.paths import hook_dir
from .common.runtime import env_int, init_hook_context
from .common.skill_enquete_state import load_state, save_state, state_path

# Debug-log ON/OFF only (writes to logs/skill_enquete_stop/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]
DEFAULT_MAX_ATTEMPTS = 3

QUESTIONS = (
    "今回のタスクでこのスキルはどの程度役に立ちましたか？期待していた内容とズレはありましたか？",
    "指示・説明・手順の中で分かりにくかった点、迷った点、無駄だと感じた点はありましたか？",
    "次回このスキルをもっと使いやすくするための改善案があれば教えてください。",
)


def build_template(skill_name, session_id):
    timestamp = datetime.now().astimezone().isoformat()
    questions_block = "\n\n".join(
        f"### Q{i}. {q}\n(ここに回答)" for i, q in enumerate(QUESTIONS, start=1)
    )
    return (
        "---\n"
        f"skill: {skill_name}\n"
        f"session_id: {session_id}\n"
        f"date: {timestamp}\n"
        "---\n\n"
        f"{questions_block}\n"
    )


def build_message(pending, session_id):
    lines = [
        "[skill-enquete] このセッションで使用したスキルのうち、frontmatterに "
        "`auto-enquete: true` が設定されているものについて、使い心地アンケートに"
        "回答してください。",
        "各スキルにつき、下記の保存先パスへ Write ツールで新規Markdownファイルを"
        "作成し、テンプレートの `(ここに回答)` を実際の回答に置き換えて保存して"
        "ください。プレースホルダのまま残さないこと。ユーザーへの確認は不要です。",
        "全て保存し終えたら、通常どおり応答を終了してください。",
        "",
    ]
    for item in pending:
        lines.append(f"## スキル: {item['name']}")
        lines.append(f"保存先（このパスへWriteで新規作成）: {item['target']}")
        lines.append("")
        lines.append("テンプレート:")
        lines.append("```markdown")
        lines.append(build_template(item["name"], session_id))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main():
    payload, log, finish = init_hook_context(SCRIPT_NAME, ENABLE_HOOK_LOG)

    log["stop_hook_active"] = payload.get("stop_hook_active")

    session_id = payload.get("session_id")
    if not session_id:
        finish(0, reason="no session_id in payload")

    state_file = state_path(hook_dir(), session_id)
    if not state_file.is_file():
        finish(0, reason="no tracked skill usage this session")

    data = load_state(state_file)
    skills = data["skills"]
    if not skills:
        finish(0, reason="tracked skills empty")

    pending = []
    for name, info in sorted(skills.items()):
        skill_dir = info.get("dir") if isinstance(info, dict) else None
        if not isinstance(skill_dir, str) or not skill_dir:
            continue
        target = Path(skill_dir) / "enquete" / f"{session_id}.md"
        if target.is_file():
            continue
        pending.append({"name": name, "target": target.as_posix()})

    log["tracked_skills"] = list(skills.keys())
    log["pending_skills"] = [p["name"] for p in pending]

    if not pending:
        finish(0, reason="all tracked skills already surveyed this session")

    max_attempts = env_int("SKILL_ENQUETE_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)
    attempts = data["stop_attempts"]
    if attempts >= max_attempts:
        skipped = ", ".join(p["name"] for p in pending)
        finish(
            0,
            output={
                "systemMessage": (
                    "[skill-enquete] 未回答のスキルアンケートが残っていますが、"
                    f"最大試行回数({max_attempts}回)に達したため今回は諦めます: {skipped}"
                )
            },
            reason="max attempts reached",
            skipped=skipped,
        )

    data["stop_attempts"] = attempts + 1
    save_state(state_file, data)

    message = build_message(pending, session_id)
    print(message, file=sys.stderr)
    finish(2, reason="blocked: pending skill enquete", attempt=attempts + 1)


if __name__ == "__main__":
    main()
