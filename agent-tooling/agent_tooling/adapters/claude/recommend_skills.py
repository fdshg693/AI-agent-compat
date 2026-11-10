#!/usr/bin/env python3
"""UserPromptSubmit hook that recommends potentially-relevant skills.

Every time the user submits a prompt, this hook:

1. Reads `config/recommend_skills.yaml` for a list of `roots`
   (repo-relative directories) to search. The scope is fully config-driven --
   it is not tied to `.claude/skills` and does not have to include it at all.
2. Recursively collects every `SKILL.md` under those roots and reads its
   `name` / `description` from YAML frontmatter (this includes skills
   belonging to plugins that are not currently enabled in this session --
   those cannot be invoked via the Skill tool, which is why recommendations
   below are given as file paths to `Read`, not skill names to invoke).
3. Sends the user's prompt plus the collected (name, description) pairs to
   an AI model via `aim_cli` (tools/aim), imported as a library (not the
   `aim` CLI subprocess) so batches can be judged concurrently with
   `asyncio.gather`. If there are more skills than one batch can reasonably
   hold, they are split into batches (default 30 skills each; see env vars
   below) and judged in parallel, each as its own independent aim call.
4. Any skills the model judged relevant are attached via `additionalContext`
   as `<absolute path> (<name>): <reason>` lines, so Claude can `Read` the
   file directly regardless of whether that skill is registered with the
   Skill tool in this session.

This hook must run via `uv run --project ${CLAUDE_PROJECT_DIR} <script>`
(`runner: uv-project` in `scenarios/recommend_skills/hook.yaml`), NOT bare `python`: `aim_cli` is only
importable inside this repo's root `.venv` (a uv workspace member, see
`pyproject.toml`), and `uv run --project` resolves/activates that venv
regardless of the hook's working directory.

Falls through silently (exits 0, no additionalContext added) whenever
recommending isn't applicable or fails: empty prompt, no config file, no
`roots` configured, no `SKILL.md` found under the configured roots, no
skill judged relevant, `aim_cli` not importable, or any aim/timeout error
(including a missing OPENROUTER_API_KEY, which `aim_cli` itself reports via
`AimError`). This hook must never be the reason a prompt fails to reach
Claude.
"""

"""
以下を前提とする:
- `tools/aim` がこのリポジトリの uv workspace メンバーであること（`pyproject.toml`
  参照）。`uv run --project ${CLAUDE_PROJECT_DIR} ...` 経由であれば追加のインストール
  操作なしに `aim_cli` が import できる
- OPENROUTER_API_KEY 環境変数（または `tools/aim/.env`）設定済み
- `config/recommend_skills.yaml` に少なくとも1つ有効な `roots` エントリ
  があること（無ければこのフックは何もしない）
"""

"""
環境変数（すべて省略可）:
- `AIM_SKILL_RECOMMEND_MODEL`          `aim_cli.MODELS` のキー（デフォルト: mini-m3。
                                       不明な値が指定された場合はデフォルトにフォール
                                       バックする）
- `AIM_SKILL_RECOMMEND_BATCH_SIZE`     1回のaim呼び出しに含めるスキル件数（デフォルト: 30）
- `AIM_SKILL_RECOMMEND_MAX_CONCURRENCY` 同時に投げるaim呼び出しの並列数（デフォルト: 4）
- `AIM_SKILL_RECOMMEND_TIMEOUT`        aim呼び出し1回あたりのタイムアウト秒数
                                       （デフォルト: 45。フック自体の`timeout`設定値
                                       より十分小さくすること）
- `AIM_SKILL_RECOMMEND_MAX_PROMPT_CHARS` aimに送るプロンプト本文の上限文字数、超過分は
                                       末尾切り捨て（デフォルト: 4000）
- `AIM_SKILL_RECOMMEND_MAX_SKILLS`     収集するスキル件数の上限（デフォルト: 300。
                                       超過分は走査を打ち切り、警告のみ記録する）
- `HOOK_LOG`                           このフックの「デバッグログ」（詳細ログ）を
                                       配置先ディレクトリの`logs/recommend_skills/` に
                                       書き出すかどうか（true/false等）。フック自体の
                                       有効/無効ではない（そちらは登録の有無で決まる）。
                                       未設定ならスクリプト先頭の`ENABLE_HOOK_LOG`に従う。
                                       配置先ディレクトリの`.env`に設定されていればそちらが優先。
"""
import asyncio
import os

import yaml

from agent_tooling.core.fs_links import find_files

from .common.paths import hook_dir, resolve_project_dir
from .common.runtime import env_int, init_hook_context
from .common.skill_frontmatter import read_frontmatter

# Debug-log ON/OFF only (writes to logs/recommend_skills/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

DEFAULT_MODEL = "mini-m3"
DEFAULT_BATCH_SIZE = 30
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_TIMEOUT = 45
DEFAULT_MAX_PROMPT_CHARS = 4000
DEFAULT_MAX_SKILLS = 300

JUDGE_INSTRUCTIONS = (
    "You are a skill-routing assistant embedded in a coding tool (Claude Code). "
    "You will be given a user's prompt submitted to an AI coding assistant, and "
    "a list of available skills (name + one-line description) that the "
    "assistant could read for extra guidance on this specific task. Decide "
    "which of the listed skills, if any, are plausibly relevant to the user's "
    "prompt -- meaning reading that skill's instructions would likely help "
    "handle this request well. Be selective: most prompts match zero or very "
    "few skills. Only pick a skill when its description clearly matches what "
    "the user is asking for.\n\n"
    "Output ONLY lines in exactly this format, one per relevant skill, no "
    "other text, no markdown, no numbering, no preamble:\n"
    "<skill_name> :: <short reason, one line, same language as the user's prompt>\n\n"
    "Use skill names EXACTLY as given in the list below -- never invent a name "
    "that isn't listed. If no skill is relevant, output nothing at all."
)


def read_skill(skill_md_path):
    frontmatter = read_frontmatter(skill_md_path)
    if frontmatter is None:
        return None
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        return None
    name = frontmatter.get("name")
    if not isinstance(name, str) or not name.strip():
        name = skill_md_path.parent.name
    return {
        "name": name.strip(),
        "description": description.strip(),
        "path": skill_md_path.as_posix(),
    }


def collect_skills(project_dir, roots, max_skills, warnings):
    by_name = {}
    for root in roots:
        root_path = (project_dir / root).resolve()
        if not root_path.is_dir():
            continue
        for skill_md_path in sorted(find_files(root_path, "SKILL.md")):
            entry = read_skill(skill_md_path)
            if entry is None or entry["name"] in by_name:
                continue
            by_name[entry["name"]] = entry
            if len(by_name) >= max_skills:
                warnings.append(
                    f"skill scan capped at {max_skills}; some SKILL.md files "
                    "under the configured roots were not considered"
                )
                return list(by_name.values())
    return list(by_name.values())


def make_batches(skills, batch_size):
    ordered = sorted(skills, key=lambda s: s["name"])
    return [ordered[i : i + batch_size] for i in range(0, len(ordered), batch_size)]


def build_batch_prompt(prompt_text, batch):
    skills_block = "\n".join(f"- {s['name']}: {s['description']}" for s in batch)
    return (
        f"{JUDGE_INSTRUCTIONS}\n\n"
        f"---\nUser's prompt:\n{prompt_text}\n---\n\n"
        f"Available skills:\n{skills_block}\n---"
    )


def parse_recommendations(response_text, batch):
    by_name = {s["name"]: s for s in batch}
    by_name_lower = {s["name"].lower(): s for s in batch}
    seen = set()
    results = []
    for line in response_text.splitlines():
        line = line.strip().lstrip("-*").strip()
        if "::" not in line:
            continue
        raw_name, _, reason = line.partition("::")
        raw_name = raw_name.strip().strip("`").strip()
        skill = by_name.get(raw_name) or by_name_lower.get(raw_name.lower())
        if skill is None or skill["name"] in seen:
            continue
        seen.add(skill["name"])
        results.append({**skill, "reason": reason.strip() or "(no reason given)"})
    return results


async def judge_all(prompt_text, batches, model, timeout, max_concurrency, warnings):
    from aim_cli import MODELS, AimError, call_async, create_client

    model_id = MODELS[model]
    semaphore = asyncio.Semaphore(max_concurrency)

    async def judge_one(client, batch):
        batch_prompt = build_batch_prompt(prompt_text, batch)
        async with semaphore:
            try:
                text = await asyncio.wait_for(
                    call_async(client, model_id, batch_prompt), timeout=timeout
                )
            except asyncio.TimeoutError:
                warnings.append(f"batch of {len(batch)} skills timed out after {timeout}s")
                return []
            except AimError as e:
                warnings.append(f"aim call failed for a batch of {len(batch)} skills: {e}")
                return []
        return parse_recommendations(text, batch)

    async with create_client() as client:
        batch_results = await asyncio.gather(*(judge_one(client, b) for b in batches))

    merged = []
    for batch_result in batch_results:
        merged.extend(batch_result)
    return merged


def main():
    payload, log, finish = init_hook_context(SCRIPT_NAME, ENABLE_HOOK_LOG)

    log["hook_event_name"] = payload.get("hook_event_name")
    if payload.get("hook_event_name") != "UserPromptSubmit":
        finish(0, reason="not a UserPromptSubmit event")

    prompt = payload.get("prompt")
    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        finish(0, reason="empty prompt")

    project_dir = resolve_project_dir(payload)
    config_path = hook_dir() / "config" / f"{SCRIPT_NAME}.yaml"
    if not config_path.is_file():
        finish(0, reason="config not found", path=str(config_path))

    try:
        config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        finish(0, reason="failed to read/parse config", error=str(e))

    roots = (config_data or {}).get("roots") if isinstance(config_data, dict) else None
    roots = (
        [r for r in roots if isinstance(r, str) and r.strip()] if isinstance(roots, list) else []
    )
    if not roots:
        finish(0, reason="no roots configured")

    warnings = []
    max_skills = env_int("AIM_SKILL_RECOMMEND_MAX_SKILLS", DEFAULT_MAX_SKILLS)
    skills = collect_skills(project_dir, roots, max_skills, warnings)
    log["skills_found"] = len(skills)
    if not skills:
        finish(0, reason="no SKILL.md found under configured roots", roots=roots)

    try:
        from aim_cli import MODELS
    except ImportError as e:
        finish(
            0,
            reason="aim_cli not importable (must run via `uv run --project`)",
            error=str(e),
        )

    model = os.environ.get("AIM_SKILL_RECOMMEND_MODEL", DEFAULT_MODEL)
    if model not in MODELS:
        model = DEFAULT_MODEL

    max_prompt_chars = env_int("AIM_SKILL_RECOMMEND_MAX_PROMPT_CHARS", DEFAULT_MAX_PROMPT_CHARS)
    truncated_prompt = prompt
    if len(truncated_prompt) > max_prompt_chars:
        truncated_prompt = truncated_prompt[:max_prompt_chars] + "\n\n[prompt truncated]"

    batch_size = env_int("AIM_SKILL_RECOMMEND_BATCH_SIZE", DEFAULT_BATCH_SIZE)
    batches = make_batches(skills, batch_size)
    max_concurrency = env_int("AIM_SKILL_RECOMMEND_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY)
    timeout = env_int("AIM_SKILL_RECOMMEND_TIMEOUT", DEFAULT_TIMEOUT)
    log["model"] = model
    log["batch_count"] = len(batches)
    log["batch_size"] = batch_size

    try:
        recommendations = asyncio.run(
            judge_all(truncated_prompt, batches, model, timeout, max_concurrency, warnings)
        )
    except SystemExit as e:
        # aim_cli.resolve_api_key() calls sys.exit(1) directly (not an
        # exception) when OPENROUTER_API_KEY is unset, since it also serves
        # the CLI entrypoint. Treat that the same as any other aim failure.
        finish(
            0,
            reason="aim_cli exited (likely missing OPENROUTER_API_KEY)",
            code=e.code,
            warnings=warnings,
        )
    except Exception as e:
        finish(0, reason="aim judging failed", error=repr(e), warnings=warnings)

    log["warnings"] = warnings
    log["recommendations"] = [r["name"] for r in recommendations]
    if not recommendations:
        finish(0, reason="no relevant skills", skills_scanned=len(skills), warnings=warnings)

    lines = [f"- {r['path']} ({r['name']}): {r['reason']}" for r in recommendations]
    additional_context = (
        "[recommend-skills] このプロンプトに関連しそうなスキルを、設定済みの探索範囲"
        "（フック配置先の config/recommend_skills.yaml のroots）からAI (aim/"
        f"{model}) が選定しました。Skillツールに登録されていない可能性があるため、"
        "まず対象のSKILL.mdをReadして内容を確認し、実際に関連していれば活用してください:\n\n"
        + "\n".join(lines)
    )

    result = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        }
    }
    finish(0, output=result, reason="recommended", warnings=warnings)


if __name__ == "__main__":
    main()
