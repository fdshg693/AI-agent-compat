#!/usr/bin/env python3
"""PreToolUse + PreInvocation hook: record touched paths, then inject AGENTS.md.

Antigravity PreToolUse has a required decision field and no injection slot.
This adapter always returns {"decision":"allow"} on PreToolUse (never deny /
ask) and stashes AbsolutePath / TargetFile / CommandLine dirs under
conversationId. PreInvocation has no tool args; it drains that cache and
injects injectSteps[].ephemeralMessage.

Workspace-root AGENTS.md is skipped (native active-directory load). GEMINI.md
is never a candidate. Fail-open, except PreToolUse still prints decision
allow so an empty stdout cannot stall the gate.

Copy the built file from agent_tooling/hooks/generated/antigravity/nested_agents_md.py into .agents/hooks/ and
register both events in .agents/hooks.json. Cache dirs are
nested-agents-md-antigravity (seen) and nested-agents-md-antigravity-pending.
"""

import json
import os
import sys

from agent_tooling.core.bash import extract_bash_dirs
from agent_tooling.core.discovery import find_repo_root
from agent_tooling.hooks.common.cache import load_cache, save_cache
from agent_tooling.hooks.scenarios.nested_agents_md.discovery import (
    collect_nested_agents_md,
    path_to_touched_dir,
)

MAX_CONTEXT_BYTES = 16_000
CACHE_NAME = "nested-agents-md-antigravity"
PENDING_CACHE_NAME = "nested-agents-md-antigravity-pending"
NESTED_CANDIDATE_NAMES = ("AGENTS.md",)
PATH_ARG_KEYS = ("AbsolutePath", "TargetFile")


def _cwd_from_event(event):
    args = (event.get("toolCall") or {}).get("args") or {}
    cwd = args.get("Cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    workspaces = event.get("workspacePaths") or []
    if workspaces and isinstance(workspaces[0], str) and workspaces[0]:
        return workspaces[0]
    return os.getcwd()


def _root_from_event(event, cwd):
    workspaces = event.get("workspacePaths") or []
    if workspaces and isinstance(workspaces[0], str) and workspaces[0]:
        return os.path.normpath(workspaces[0])
    return find_repo_root(cwd)


def extract_touched_dirs(event, cwd):
    args = (event.get("toolCall") or {}).get("args") or {}
    if not isinstance(args, dict):
        args = {}
    dirs = set()
    for key in PATH_ARG_KEYS:
        touched = path_to_touched_dir(args.get(key), cwd)
        if touched:
            dirs.add(touched)
    command = args.get("CommandLine")
    if isinstance(command, str) and command:
        dirs |= extract_bash_dirs(command, cwd)
    return dirs


def add_pending(session_id, dirs):
    cache_path, seen = load_cache(session_id, PENDING_CACHE_NAME)
    save_cache(
        cache_path,
        seen | {os.path.normpath(d) for d in dirs if d},
    )


def take_pending(session_id):
    cache_path, seen = load_cache(session_id, PENDING_CACHE_NAME)
    save_cache(cache_path, set())
    return seen


def render_ephemeral(found):
    parts = []
    total = 0
    for rel, content in found:
        block = f"{rel}:\n{content}\n"
        if total + len(block) > MAX_CONTEXT_BYTES:
            parts.append(
                f"(truncated: remaining AGENTS.md files omitted, over {MAX_CONTEXT_BYTES} bytes)"
            )
            break
        parts.append(block)
        total += len(block)
    return (
        "The following nested AGENTS.md files apply to paths touched since "
        "the last model invocation:\n\n" + "\n".join(parts)
    )


def _print(obj):
    print(json.dumps(obj))


def handle_pre_tool_use(event):
    cwd = _cwd_from_event(event)
    session_id = event.get("conversationId") or "unknown"
    touched = extract_touched_dirs(event, cwd)
    if touched:
        add_pending(session_id, touched)
    _print({"decision": "allow"})
    return 0


def handle_pre_invocation(event):
    cwd = _cwd_from_event(event)
    session_id = event.get("conversationId") or "unknown"
    pending = take_pending(session_id)
    if not pending:
        _print({})
        return 0

    root = _root_from_event(event, cwd)
    found = collect_nested_agents_md(
        root,
        pending,
        {root},
        session_id,
        CACHE_NAME,
        candidate_names=NESTED_CANDIDATE_NAMES,
    )
    if not found:
        _print({})
        return 0

    _print({"injectSteps": [{"ephemeralMessage": render_ephemeral(found)}]})
    return 0


def _run():
    try:
        event = json.load(sys.stdin)
    except Exception:
        _print({"decision": "allow"})
        return 0

    if isinstance(event.get("toolCall"), dict):
        return handle_pre_tool_use(event)
    if "invocationNum" in event:
        return handle_pre_invocation(event)
    # Unknown payload: fail-open without stalling a PreToolUse gate.
    _print({"decision": "allow"})
    return 0


def main():
    try:
        return _run()
    except Exception:
        try:
            _print({"decision": "allow"})
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
