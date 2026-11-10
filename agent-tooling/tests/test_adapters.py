"""Adapter stdin/stdout contracts. Does not start GUI agents."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "agent_tooling"
GENERATED = PACKAGE_ROOT / "hooks" / "generated"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    for rel, content in files.items():
        _write(repo / rel, content)
    return repo


def run_complete(agent: str, payload: dict, scenario: str = "nested_agents_md") -> tuple[int, str]:
    script = GENERATED / agent / f"{scenario}.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout


def test_codex_bash_injects_nested_agents_md(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {"pkg/file.py": "x\n", "pkg/AGENTS.md": "from-pkg\n"},
    )
    code, stdout = run_complete(
        "codex",
        {
            "cwd": str(repo),
            "session_id": f"adapter-codex-{tmp_path.name}",
            "tool_name": "Bash",
            "tool_input": {"command": "cat pkg/file.py"},
        },
    )
    assert code == 0
    body = json.loads(stdout)
    ctx = body["hookSpecificOutput"]["additionalContext"]
    assert body["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "pkg/AGENTS.md:" in ctx
    assert "from-pkg" in ctx


def test_codex_untouched_exits_silent(tmp_path: Path):
    repo = make_repo(tmp_path, {"pkg/file.py": "x\n"})
    code, stdout = run_complete(
        "codex",
        {
            "cwd": str(repo),
            "session_id": f"adapter-codex-empty-{tmp_path.name}",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
        },
    )
    assert code == 0
    assert stdout.strip() == ""


def test_claude_read_injects_agents_md(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {"pkg/file.py": "x\n", "pkg/AGENTS.md": "claude-pkg\n"},
    )
    code, stdout = run_complete(
        "claude",
        {
            "cwd": str(repo),
            "session_id": f"adapter-claude-{tmp_path.name}",
            "tool_name": "Read",
            "tool_input": {"file_path": "pkg/file.py"},
        },
    )
    assert code == 0
    body = json.loads(stdout)
    ctx = body["hookSpecificOutput"]["additionalContext"]
    assert body["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in body
    assert "pkg/AGENTS.md:" in ctx
    assert "claude-pkg" in ctx


def test_claude_skips_dir_with_claude_md(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {
            "pkg/file.py": "x\n",
            "pkg/AGENTS.md": "should-skip\n",
            "pkg/CLAUDE.md": "@./AGENTS.md\n",
        },
    )
    code, stdout = run_complete(
        "claude",
        {
            "cwd": str(repo),
            "session_id": f"adapter-claude-skip-{tmp_path.name}",
            "tool_name": "Read",
            "tool_input": {"file_path": "pkg/file.py"},
        },
    )
    assert code == 0
    assert stdout.strip() == ""


def test_cursor_post_tool_use_additional_context(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {
            "AGENTS.md": "root-agents\n",
            "pkg/file.py": "x\n",
            "pkg/AGENTS.md": "cursor-pkg\n",
        },
    )
    code, stdout = run_complete(
        "cursor",
        {
            "cwd": str(repo),
            "conversation_id": f"adapter-cursor-{tmp_path.name}",
            "tool_name": "Read",
            "tool_input": {"path": "pkg/file.py"},
        },
    )
    assert code == 0
    body = json.loads(stdout)
    assert set(body) == {"additional_context"}
    ctx = body["additional_context"]
    assert "pkg/AGENTS.md:" in ctx
    assert "cursor-pkg" in ctx
    assert "root-agents" not in ctx
    assert "permission" not in body
    assert "updated_input" not in body


def test_antigravity_pre_tool_use_then_pre_invocation(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {"pkg/file.py": "x\n", "pkg/AGENTS.md": "ag-pkg\n"},
    )
    session = f"adapter-ag-{tmp_path.name}"
    pre_code, pre_out = run_complete(
        "antigravity",
        {
            "conversationId": session,
            "workspacePaths": [str(repo)],
            "toolCall": {"args": {"AbsolutePath": str(repo / "pkg" / "file.py")}},
        },
    )
    assert pre_code == 0
    assert json.loads(pre_out) == {"decision": "allow"}

    inv_code, inv_out = run_complete(
        "antigravity",
        {
            "conversationId": session,
            "workspacePaths": [str(repo)],
            "invocationNum": 1,
        },
    )
    assert inv_code == 0
    body = json.loads(inv_out)
    msg = body["injectSteps"][0]["ephemeralMessage"]
    assert "pkg/AGENTS.md:" in msg
    assert "ag-pkg" in msg


def test_antigravity_pre_invocation_without_pending_is_empty(tmp_path: Path):
    repo = make_repo(tmp_path, {"pkg/file.py": "x\n"})
    code, stdout = run_complete(
        "antigravity",
        {
            "conversationId": f"adapter-ag-empty-{tmp_path.name}",
            "workspacePaths": [str(repo)],
            "invocationNum": 1,
        },
    )
    assert code == 0
    assert json.loads(stdout) == {}


def test_kilo_python_returns_additional_context(tmp_path: Path):
    repo = make_repo(
        tmp_path,
        {"pkg/file.py": "x\n", "pkg/AGENTS.md": "kilo-pkg\n"},
    )
    code, stdout = run_complete(
        "kilo",
        {
            "cwd": str(repo),
            "session_id": f"adapter-kilo-{tmp_path.name}",
            "tool_name": "read",
            "tool_input": {"filePath": "pkg/file.py"},
        },
    )
    assert code == 0
    body = json.loads(stdout)
    assert set(body) == {"additionalContext"}
    assert "pkg/AGENTS.md:" in body["additionalContext"]
    assert "kilo-pkg" in body["additionalContext"]


def test_kilo_python_empty_context_when_nothing_found(tmp_path: Path):
    repo = make_repo(tmp_path, {"pkg/file.py": "x\n"})
    code, stdout = run_complete(
        "kilo",
        {
            "cwd": str(repo),
            "session_id": f"adapter-kilo-empty-{tmp_path.name}",
            "tool_name": "read",
            "tool_input": {"filePath": "pkg/file.py"},
        },
    )
    assert code == 0
    assert json.loads(stdout) == {"additionalContext": ""}


def test_kilo_ts_spawn_contract():
    text = (GENERATED / "kilo" / "nested_agents_md.ts").read_text(encoding="utf-8")
    assert "spawnSync" in text
    assert "additionalContext" in text
    assert "<system-reminder>" in text
    assert "output.output" in text
    assert "output.args =" not in text
    assert "throw" not in text
    assert "input.tool" in text
    assert "python" in text
    assert "python3" in text


def _rule_fixture(tmp_path: Path) -> Path:
    return make_repo(
        tmp_path,
        {
            ".claude/rules/python.md": '---\npaths:\n  - "**/*.py"\n---\nscoped-rule\n',
            "pkg/file.py": "x\n",
        },
    )


def test_scoped_codex_apply_patch_accepts_new_path(tmp_path: Path):
    repo = _rule_fixture(tmp_path)
    code, stdout = run_complete(
        "codex",
        {
            "cwd": str(repo),
            "session_id": f"scoped-codex-{tmp_path}",
            "tool_name": "apply_patch",
            "tool_input": {"command": "*** Add File: new.py\n"},
        },
        "scoped_rules",
    )
    assert code == 0
    assert "scoped-rule" in json.loads(stdout)["hookSpecificOutput"]["additionalContext"]


def test_scoped_claude_read_uses_additional_context(tmp_path: Path):
    repo = _rule_fixture(tmp_path)
    code, stdout = run_complete(
        "claude",
        {
            "cwd": str(repo),
            "session_id": f"scoped-claude-{tmp_path}",
            "tool_name": "Read",
            "tool_input": {"file_path": "pkg/file.py"},
        },
        "scoped_rules",
    )
    assert code == 0
    assert "scoped-rule" in json.loads(stdout)["hookSpecificOutput"]["additionalContext"]


def test_scoped_cursor_and_kilo_output_contracts(tmp_path: Path):
    repo = _rule_fixture(tmp_path)
    for agent, key in (("cursor", "additional_context"), ("kilo", "additionalContext")):
        code, stdout = run_complete(
            agent,
            {
                "cwd": str(repo),
                "session_id": f"scoped-{agent}-{tmp_path}",
                "tool_name": "read",
                "tool_input": {"path": "pkg/file.py", "filePath": "pkg/file.py"},
            },
            "scoped_rules",
        )
        assert code == 0
        assert "scoped-rule" in json.loads(stdout)[key]


def test_scoped_antigravity_buffers_until_invocation(tmp_path: Path):
    repo = _rule_fixture(tmp_path)
    session = f"scoped-ag-{tmp_path.name}-{abs(hash(str(tmp_path)))}"
    code, stdout = run_complete(
        "antigravity",
        {
            "conversationId": session,
            "workspacePaths": [str(repo)],
            "toolCall": {"args": {"TargetFile": str(repo / "pkg/file.py")}},
        },
        "scoped_rules",
    )
    assert code == 0
    assert json.loads(stdout) == {"decision": "allow"}
    code, stdout = run_complete(
        "antigravity",
        {"conversationId": session, "workspacePaths": [str(repo)], "invocationNum": 1},
        "scoped_rules",
    )
    assert code == 0
    assert "scoped-rule" in json.loads(stdout)["injectSteps"][0]["ephemeralMessage"]


def test_scoped_bash_with_no_recognizable_path_is_silent(tmp_path: Path):
    repo = _rule_fixture(tmp_path)
    code, stdout = run_complete(
        "codex",
        {
            "cwd": str(repo),
            "session_id": f"scoped-codex-empty-{tmp_path}",
            "tool_name": "Bash",
            "tool_input": {"command": "echo 'not a file read'"},
        },
        "scoped_rules",
    )
    assert code == 0
    assert stdout.strip() == ""
