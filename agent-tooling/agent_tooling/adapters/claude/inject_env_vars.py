#!/usr/bin/env python3
"""PreToolUse hook for the Bash / PowerShell tools.

Reads `config/inject_env_vars.yaml` (next to the installed hook) and prepends
`export KEY='value'` (Bash) / `$env:KEY='value'` (PowerShell) statements to
the command before it runs, so declared env vars are always present without
the user having to `source` anything manually.

Never blocks the command: a missing config file, a bad reference, or a
missing key in a referenced dotenv file just skips that one variable and
reports a warning via `systemMessage` -- the original command still runs.

`config/` holds one YAML file per hook that needs one, named
after the hook script (`<script_name>.yaml`); see the comments in
`inject_env_vars.yaml` (seeded on install) for this file's format.
"""

"""
環境変数（省略可、配置先ディレクトリの `.env` で設定）:
- `HOOK_LOG`             このフックの「デバッグログ」を 配置先ディレクトリの`logs/inject_env_vars/` に
                         書き出すかどうか（true/false等）。フック自体の有効/無効ではない
                         （そちらは登録の有無で決まる）。
                         未設定ならスクリプト先頭の `ENABLE_HOOK_LOG` に従う。
- `NOTIFY_INJECTED_VARS` 環境変数を実際に注入/上書きした際、どのキーを注入したかを
                         `systemMessage` で通知するかどうか（true/false等）。
                         未設定ならスクリプト先頭の `ENABLE_INJECT_NOTIFY` に従う
                         （デフォルト true）。
"""
import os
import re

from .common.dotenv import load_dotenv_value, strip_quotes
from .common.hook_log import TRUTHY, resolve_bool_flag
from .common.paths import hook_dir
from .common.runtime import init_hook_context

# Debug-log ON/OFF only (writes to logs/inject_env_vars/ next to this hook) --
# NOT whether this hook itself runs (that's whether it is registered).
# HOOK_LOG in the `.env` next to this hook, if set, overrides this default.
ENABLE_HOOK_LOG = False

# Whether to report (via systemMessage) which keys were actually injected or
# overridden. NOTIFY_INJECTED_VARS in the `.env` next to this hook, if set, overrides
# this default.
ENABLE_INJECT_NOTIFY = True

SCRIPT_NAME = os.path.splitext(os.path.basename(__file__))[0]

COMMAND_TOOLS = {"Bash", "PowerShell"}

# Deliberately NOT using pyyaml here: this hook runs before every single
# Bash/PowerShell call, so it must start instantly with the bare `python`
# this repo's other hooks use (no dependency install/venv resolution).
# Only a narrow subset of YAML is supported: a top-level `override` scalar
# and a top-level `vars` mapping of `KEY: value` pairs, one level deep, no
# lists/anchors/flow-style/multiline strings. `key: value` must have the
# colon followed by a space (standard YAML block-mapping style) -- values
# containing ":" (e.g. URLs) still parse correctly as long as that holds.
TOP_KEY_RE = re.compile(r"^(\S+):\s*(.*)$")
NESTED_KEY_RE = re.compile(r"^\s+(\S+):\s*(.*)$")


def parse_env_yaml(text):
    """Parse this hook's env.yaml subset. Returns (override: bool, vars: dict).

    Duplicate keys (top-level or within `vars`) resolve last-one-wins, same
    as real YAML.
    """
    override = False
    env_vars = {}
    section = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if line[:1].isspace():
            nested = NESTED_KEY_RE.match(line)
            if nested and section == "vars":
                key = nested.group(1)
                env_vars[key] = strip_quotes(nested.group(2))
            continue

        top = TOP_KEY_RE.match(line)
        if not top:
            continue
        key, value = top.group(1), strip_quotes(top.group(2))
        if key == "vars":
            section = "vars"
            continue
        section = None
        if key == "override":
            override = value.lower() in TRUTHY

    return override, env_vars


def resolve_value(key, raw_value, base_dir, warnings):
    if not raw_value.startswith("@"):
        return raw_value

    ref_path = (base_dir / raw_value[1:]).resolve()
    resolved = load_dotenv_value(ref_path, key)
    if resolved is None:
        warnings.append(
            f"[inject-env-vars] {key}: 参照先 '{ref_path}' にキー '{key}' が見つからないか、"
            "ファイルを読めませんでした。このキーの注入をスキップしました。"
        )
    return resolved


def build_export_prefix(tool_name, values):
    if tool_name == "PowerShell":
        lines = ["$env:{}='{}'".format(k, v.replace("'", "''")) for k, v in values.items()]
    else:
        lines = ["export {}='{}'".format(k, v.replace("'", "'\\''")) for k, v in values.items()]
    return "\n".join(lines)


def main():
    payload_in, log, finish = init_hook_context(SCRIPT_NAME, ENABLE_HOOK_LOG)

    tool_name = payload_in.get("tool_name")
    log["tool_name"] = tool_name
    if tool_name not in COMMAND_TOOLS:
        finish(0, reason="not a Bash/PowerShell call")

    tool_input = payload_in.get("tool_input") or {}
    original_command = tool_input.get("command")
    if not original_command:
        finish(0, reason="no command in tool_input")

    config_path = hook_dir() / "config" / f"{SCRIPT_NAME}.yaml"
    if not config_path.is_file():
        finish(0, reason="config not found", path=str(config_path))

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as e:
        finish(0, reason="failed to read config", error=str(e))

    override, declared_vars = parse_env_yaml(text)
    log["override"] = override
    log["declared_keys"] = list(declared_vars.keys())

    if not declared_vars:
        finish(0, reason="no vars declared")

    base_dir = config_path.parent
    warnings = []
    values = {}
    for key, raw_value in declared_vars.items():
        if not override and key in os.environ:
            continue
        resolved = resolve_value(key, raw_value, base_dir, warnings)
        if resolved is None:
            continue
        values[key] = resolved

    if not values:
        output = {"systemMessage": "\n".join(warnings)} if warnings else None
        finish(0, output=output, reason="nothing to inject", warnings=warnings)

    export_prefix = build_export_prefix(tool_name, values)
    new_command = f"{export_prefix}\n{original_command}"

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {**tool_input, "command": new_command},
        }
    }

    notify_enabled = resolve_bool_flag("NOTIFY_INJECTED_VARS", ENABLE_INJECT_NOTIFY)
    messages = list(warnings)
    if notify_enabled:
        messages.append("[inject-env-vars] 環境変数を注入しました: " + ", ".join(values.keys()))
    if messages:
        output["systemMessage"] = "\n".join(messages)

    finish(
        0,
        output=output,
        injected=list(values.keys()),
        warnings=warnings,
        notified=notify_enabled,
    )


if __name__ == "__main__":
    main()
