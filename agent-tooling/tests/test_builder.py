"""Inliner: shebang/docstring contract, no leftover hooks imports, multi-entry."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from agent_tooling.hooks.build.build import (
    CATALOG_OUTPUT,
    ENTRIES,
    Entry,
    InlineError,
    assert_complete_contract,
    build_all,
    build_entry,
    load_hook_specs,
    read_script_metadata,
    render_complete,
)
from agent_tooling.core.bash import extract_bash_dirs
from agent_tooling.core.discovery import ancestor_chain, find_repo_root
from agent_tooling.hooks.scenarios.nested_agents_md.discovery import collect_nested_agents_md

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "agent_tooling"
HOOKS_ROOT = PACKAGE_ROOT / "hooks"
REPO_ROOT = PACKAGE_ROOT.parents[2]
GENERATED_NESTED = HOOKS_ROOT / "generated" / "codex" / "nested_agents_md.py"
# Formerly .claude/hooks/*.py; behavior tests live in tests/claude_hooks/.
CLAUDE_ONLY_HOOKS = (
    "block_large_read",
    "inject_env_vars",
    "long_run_collector",
    "long_run_statement_collector",
    "stop_alert",
    "task_tracker_session",
    "summarize_read",
    "summarize_webfetch",
    "translate_prompt",
    "recommend_skills",
    "skill_usage_tracker",
    "skill_enquete_stop",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_entries_covers_complete_agents():
    names = {e.name for e in ENTRIES}
    assert len(ENTRIES) == 28
    assert names == {
        "codex:nested_agents_md",
        "claude:nested_agents_md",
        "cursor:nested_agents_md",
        "antigravity:nested_agents_md",
        "kilo:nested_agents_md",
        "claude:scoped_rules",
        "codex:scoped_rules",
        "cursor:scoped_rules",
        "antigravity:scoped_rules",
        "kilo:scoped_rules",
        "claude:agent_sessions",
        "codex:agent_sessions",
        "claude:notify",
        "cursor:agent_sessions",
        "antigravity:agent_sessions",
        "kilo:agent_sessions",
        *(f"claude:{hook_id}" for hook_id in CLAUDE_ONLY_HOOKS),
    }
    assert all(e.output.startswith("hooks/generated/") for e in ENTRIES)
    kilo = next(e for e in ENTRIES if e.name == "kilo:nested_agents_md")
    assert kilo.copies == (
        ("adapters/kilo/nested_agents_md.ts", "hooks/generated/kilo/nested_agents_md.ts"),
    )
    kilo_sessions = next(e for e in ENTRIES if e.name == "kilo:agent_sessions")
    assert kilo_sessions.copies == (
        ("adapters/kilo/agent_sessions.ts", "hooks/generated/kilo/agent_sessions.ts"),
    )


def test_generated_matches_builder_contract():
    python_outputs = [PACKAGE_ROOT / e.output for e in ENTRIES]
    assert python_outputs, "run: just --justfile agent-compat/agent-tooling/justfile generate"
    for path in python_outputs:
        assert path.is_file(), (
            f"missing {path}: run just --justfile agent-compat/agent-tooling/justfile generate"
        )
        text = path.read_text(encoding="utf-8")
        assert_complete_contract(text)
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not node.level
                assert (node.module or "").split(".")[0] != "hooks"
    for entry in ENTRIES:
        for _, dest_rel in entry.copies:
            sidecar = PACKAGE_ROOT / dest_rel
            assert sidecar.is_file(), f"missing sidecar {sidecar}"


def test_shebang_next_is_docstring():
    text = GENERATED_NESTED.read_text(encoding="utf-8")
    first, _, rest = text.partition("\n")
    assert first == "#!/usr/bin/env python3"
    assert rest.lstrip("\n").startswith('"""')


def test_complete_discovery_matches_source(tmp_path: Path):
    complete = _load("generated_codex_discovery", GENERATED_NESTED)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "file.py").write_text("x\n", encoding="utf-8")
    (pkg / "AGENTS.md").write_text("nested-body", encoding="utf-8")
    cwd = str(repo)
    command = "cat pkg/file.py"

    src_dirs = extract_bash_dirs(command, cwd)
    complete_dirs = complete.extract_bash_dirs(command, cwd)
    assert {os_norm(d) for d in src_dirs} == {os_norm(d) for d in complete_dirs}

    root = find_repo_root(cwd)
    assert complete.find_repo_root(cwd) == root
    src_chain = ancestor_chain(root, str(pkg))
    complete_chain = complete.ancestor_chain(root, str(pkg))
    assert [os_norm(p) for p in src_chain] == [os_norm(p) for p in complete_chain]

    src_found = collect_nested_agents_md(
        root,
        {str(pkg)},
        ancestor_chain(root, root),
        session_id="builder-src",
        cache_name="nested-agents-md-test-src",
    )
    complete_found = complete.collect_nested_agents_md(
        root,
        {str(pkg)},
        complete.ancestor_chain(root, root),
        session_id="builder-complete",
        cache_name="nested-agents-md-test-complete",
    )
    assert src_found == complete_found == [("pkg/AGENTS.md", "nested-body")]


def os_norm(path: str) -> str:
    import os

    return os.path.normcase(os.path.normpath(path))


def test_builder_inlines_two_entries(tmp_path: Path):
    root = tmp_path / "hooks"
    _write(
        root / "common" / "util.py",
        '"""util"""\n\nVALUE = 7\n\ndef add(n):\n    return n + VALUE\n',
    )
    _write(
        root / "agents" / "one.py",
        '#!/usr/bin/env python3\n"""one-doc"""\n\nfrom ..common.util import add\n\n'
        "def run():\n    return add(1)\n",
    )
    _write(
        root / "agents" / "two.py",
        '#!/usr/bin/env python3\n"""two-doc"""\n\nfrom ..common.util import add\n\n'
        "def run():\n    return add(2)\n",
    )
    out1 = build_entry(
        Entry(name="one", source="agents/one.py", output="complete/one/hook.py"),
        hooks_root=root,
    )
    out2 = build_entry(
        Entry(name="two", source="agents/two.py", output="complete/two/hook.py"),
        hooks_root=root,
    )
    text1 = out1.read_text(encoding="utf-8")
    text2 = out2.read_text(encoding="utf-8")
    assert_complete_contract(text1)
    assert_complete_contract(text2)
    assert text1.split("\n", 1)[1].lstrip("\n").startswith('"""one-doc"""')
    assert text2.split("\n", 1)[1].lstrip("\n").startswith('"""two-doc"""')
    one = _load("mini_one", out1)
    two = _load("mini_two", out2)
    assert one.run() == 8
    assert two.run() == 9
    assert "from .." not in text1
    assert "from agent_tooling." not in text1


def test_builder_rejects_import_outside_hooks(tmp_path: Path):
    root = tmp_path / "hooks"
    _write(
        root / "agents" / "bad.py",
        '#!/usr/bin/env python3\n"""bad"""\n\nimport requests\n\ndef run():\n    return 1\n',
    )
    with pytest.raises(InlineError, match="outside agent_tooling"):
        render_complete(root / "agents" / "bad.py", root)


def test_builder_copies_sidecars(tmp_path: Path):
    root = tmp_path / "hooks"
    _write(
        root / "agents" / "one.py",
        '#!/usr/bin/env python3\n"""one-doc"""\n\nVALUE = 1\n',
    )
    _write(root / "agents" / "one.ts", "export default 1;\n")
    build_entry(
        Entry(
            name="one",
            source="agents/one.py",
            output="complete/one/hook.py",
            copies=(("agents/one.ts", "complete/one/hook.ts"),),
        ),
        hooks_root=root,
    )
    sidecar = root / "complete" / "one" / "hook.ts"
    assert sidecar.read_text(encoding="utf-8") == "export default 1;\n"


def test_generated_has_no_hooks_docstring_contract():
    for entry in ENTRIES:
        text = (PACKAGE_ROOT / entry.output).read_text(encoding="utf-8")
        assert "<hooks>" not in text, f"{entry.output}: registrations live in hook.yaml"


def test_catalog_matches_hook_yaml_and_generated_files():
    catalog_path = PACKAGE_ROOT / CATALOG_OUTPUT
    assert catalog_path.is_file(), (
        "run: just --justfile agent-compat/agent-tooling/justfile generate"
    )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["schemaVersion"] == 1
    specs = load_hook_specs(PACKAGE_ROOT)
    hooks = {hook["id"]: hook for hook in catalog["hooks"]}
    assert set(hooks) == set(specs) == {e.key[1] for e in ENTRIES}
    for entry in ENTRIES:
        agent, hook_id = entry.key
        record = hooks[hook_id]["agents"][agent]
        rels = [f["path"] for f in record["files"] + record["seedFiles"]]
        for rel in rels:
            assert (catalog_path.parent / rel).is_file(), rel
        assert record["main"] in {f["installPath"] for f in record["files"]}
        if agent == "kilo":
            assert record["main"].endswith(".ts") and record["registrations"] == []
        else:
            assert record["registrations"], entry.name
    assert {"event": "CwdChanged"} in hooks["agent_sessions"]["agents"]["claude"]["registrations"]
    for hook_id in CLAUDE_ONLY_HOOKS:
        assert set(hooks[hook_id]["agents"]) == {"claude"}, hook_id
    not_distributable = {h for h in CLAUDE_ONLY_HOOKS if not hooks[h]["distributable"]}
    assert not_distributable == {"recommend_skills", "skill_usage_tracker", "skill_enquete_stop"}
    assert hooks["skill_usage_tracker"]["agents"]["claude"]["dependencies"] == ["pyyaml"]
    assert hooks["summarize_read"]["requiresTools"] == ["aim"]


def test_build_all_is_deterministic():
    build_all()
    first = {
        path: path.read_bytes()
        for path in (HOOKS_ROOT / "generated").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    build_all()
    second = {
        path: path.read_bytes()
        for path in (HOOKS_ROOT / "generated").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert first == second


# --- hook.yaml / catalog / PEP 723 / inliner extensions (tmp packages) ---

HOOK_YAML = """\
id: demo
description: demo hook
agents:
  claude:
    runner: {runner}
    registrations:
      - event: PreToolUse
        matcher: Read
    seed_files:
      - source: seed/demo.yaml
        path: config/demo.yaml
  kilo: {{}}
"""

PEP723 = """\
# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6.0"]
# ///
"""


def _demo_package(tmp_path: Path, *, runner: str = "python", entry_body: str | None = None):
    root = tmp_path / "repo" / "agent-tooling" / "agent_tooling"
    scenario = root / "hooks" / "scenarios" / "demo"
    _write(scenario / "hook.yaml", HOOK_YAML.format(runner=runner))
    _write(scenario / "seed" / "demo.yaml", "key: value\n")
    _write(
        root / "adapters" / "claude" / "demo.py",
        entry_body or '#!/usr/bin/env python3\n"""claude demo"""\n\nVALUE = 1\n',
    )
    _write(root / "adapters" / "kilo" / "demo.py", '#!/usr/bin/env python3\n"""kilo demo"""\n')
    _write(root / "adapters" / "kilo" / "demo.ts", "export default 1;\n")
    entries = (
        Entry(
            name="claude:demo",
            source="adapters/claude/demo.py",
            output="hooks/generated/claude/demo.py",
        ),
        Entry(
            name="kilo:demo",
            source="adapters/kilo/demo.py",
            output="hooks/generated/kilo/demo.py",
            copies=(("adapters/kilo/demo.ts", "hooks/generated/kilo/demo.ts"),),
        ),
    )
    return root, entries


def test_build_all_writes_catalog_and_seed(tmp_path: Path):
    root, entries = _demo_package(tmp_path)
    build_all(hooks_root=root, entries=entries)
    generated = root / "hooks" / "generated"
    seed = generated / "claude" / "seed" / "demo" / "config" / "demo.yaml"
    assert seed.read_text(encoding="utf-8") == "key: value\n"
    catalog = json.loads((generated / "catalog.json").read_text(encoding="utf-8"))
    (hook,) = catalog["hooks"]
    assert hook["id"] == "demo" and hook["distributable"] is True
    assert hook["agents"]["claude"] == {
        "runner": "python",
        "main": "demo.py",
        "files": [{"path": "claude/demo.py", "installPath": "demo.py"}],
        "seedFiles": [
            {"path": "claude/seed/demo/config/demo.yaml", "installPath": "config/demo.yaml"}
        ],
        "dependencies": [],
        "registrations": [{"event": "PreToolUse", "matcher": "Read"}],
    }
    assert hook["agents"]["kilo"]["main"] == "demo.ts"
    build_all(check=True, hooks_root=root, entries=entries)
    seed.write_text("drift\n", encoding="utf-8")
    with pytest.raises(InlineError, match="drift"):
        build_all(check=True, hooks_root=root, entries=entries)


def test_build_all_rejects_entries_that_disagree_with_hook_yaml(tmp_path: Path):
    root, entries = _demo_package(tmp_path)
    extra_agent = Entry(
        name="codex:demo", source="adapters/claude/demo.py", output="hooks/generated/codex/demo.py"
    )
    with pytest.raises(InlineError, match="hook.yaml agents"):
        build_all(hooks_root=root, entries=(*entries, extra_agent))
    no_yaml = Entry(
        name="claude:other", source="adapters/claude/demo.py", output="hooks/generated/x.py"
    )
    with pytest.raises(InlineError, match="no hooks/scenarios/<id>/hook.yaml"):
        build_all(hooks_root=root, entries=(*entries, no_yaml))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "matcher: Read",
            "matcher: Read\n        command: python x.py",
            "must not contain command",
        ),
        ("runner: python", "runner: node", "runner must be one of"),
        ("id: demo", "id: other", "directory name"),
        ("  kilo: {}", "  kilo:\n    registrations: [{event: x}]", "kilo has no registrations"),
        ("matcher: Read", "matcher: Read\n        bogus: 1", "unknown agents.claude.registrations"),
        ("path: config/demo.yaml", "path: ../demo.yaml", "without '..'"),
        ("description: demo hook", "description: demo hook\nrequires_tools: [nope]", "repo-tools"),
        ("runner: python", "runner: uv-project", "set distributable: false"),
    ],
)
def test_hook_yaml_validation(tmp_path: Path, old, new, message):
    root, entries = _demo_package(tmp_path)
    (tmp_path / "repo" / "registry").mkdir(parents=True, exist_ok=True)
    (tmp_path / "repo" / "registry" / "repo-tools.yaml").write_text(
        "tools:\n  aim: {}\n", encoding="utf-8"
    )
    path = root / "hooks" / "scenarios" / "demo" / "hook.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
    with pytest.raises(InlineError, match=message):
        build_all(hooks_root=root, entries=entries)


def test_pep723_dependencies_allow_third_party_import(tmp_path: Path):
    body = (
        "#!/usr/bin/env python3\n"
        + PEP723
        + '"""yaml demo"""\n\nimport json\nimport yaml\n\nVALUE = (json, yaml)\n'
    )
    root, entries = _demo_package(tmp_path, runner="uv-script", entry_body=body)
    assert read_script_metadata(body).import_names == {"yaml"}
    build_all(hooks_root=root, entries=entries)
    text = (root / "hooks" / "generated" / "claude" / "demo.py").read_text(encoding="utf-8")
    assert_complete_contract(text)
    assert text.startswith("#!/usr/bin/env python3\n" + PEP723 + '"""yaml demo"""')
    assert text.count("# /// script") == 1
    assert "import yaml" in text
    catalog = json.loads((root / CATALOG_OUTPUT).read_text(encoding="utf-8"))
    claude = catalog["hooks"][0]["agents"]["claude"]
    assert claude["runner"] == "uv-script"
    assert claude["dependencies"] == ["PyYAML>=6.0"]


def test_pep723_block_and_uv_script_runner_go_together(tmp_path: Path):
    body = "#!/usr/bin/env python3\n" + PEP723 + '"""yaml demo"""\n'
    root, entries = _demo_package(tmp_path / "a", runner="python", entry_body=body)
    with pytest.raises(InlineError, match="must not have a PEP 723"):
        build_all(hooks_root=root, entries=entries)
    root, entries = _demo_package(tmp_path / "b", runner="uv-script")
    with pytest.raises(InlineError, match="requires a PEP 723"):
        build_all(hooks_root=root, entries=entries)


def test_pep723_block_only_in_entry_module(tmp_path: Path):
    root = tmp_path / "pkg"
    _write(root / "common" / "util.py", PEP723 + '"""util"""\n\nVALUE = 1\n')
    _write(
        root / "agents" / "one.py",
        '#!/usr/bin/env python3\n"""one"""\n\nfrom ..common.util import VALUE\n',
    )
    with pytest.raises(InlineError, match="only the entry module"):
        render_complete(root / "agents" / "one.py", root)


def test_undeclared_import_inside_function_is_rejected(tmp_path: Path):
    root = tmp_path / "pkg"
    _write(
        root / "agents" / "one.py",
        '#!/usr/bin/env python3\n"""one"""\n\ndef run():\n    import requests\n    return requests\n',
    )
    with pytest.raises(InlineError, match="import requests is outside"):
        render_complete(root / "agents" / "one.py", root)
    assert "import requests" in render_complete(
        root / "agents" / "one.py", root, frozenset({"requests"})
    )


def test_relative_import_inside_function_is_rejected(tmp_path: Path):
    root = tmp_path / "pkg"
    _write(root / "common" / "util.py", '"""util"""\n\nVALUE = 1\n')
    _write(
        root / "agents" / "one.py",
        '#!/usr/bin/env python3\n"""one"""\n\ndef run():\n    from ..common import util\n'
        "    return util\n",
    )
    with pytest.raises(InlineError, match="move it to module top level"):
        render_complete(root / "agents" / "one.py", root)


def test_inlined_main_guard_is_dropped(tmp_path: Path):
    root = tmp_path / "pkg"
    _write(
        root / "common" / "util.py",
        '"""util"""\n\nVALUE = 1\n\nif __name__ == "__main__":\n    print("util main")\n',
    )
    _write(
        root / "agents" / "one.py",
        '#!/usr/bin/env python3\n"""one"""\n\nfrom ..common.util import VALUE\n\n'
        'if __name__ == "__main__":\n    print(VALUE)\n',
    )
    text = render_complete(root / "agents" / "one.py", root)
    assert "util main" not in text
    assert text.count('if __name__ == "__main__":') == 1


def test_top_level_name_collision_is_rejected(tmp_path: Path):
    root = tmp_path / "pkg"
    _write(
        root / "common" / "util.py", '"""util"""\n\nLIMIT = 1\n\ndef helper():\n    return LIMIT\n'
    )
    _write(
        root / "agents" / "one.py",
        '#!/usr/bin/env python3\n"""one"""\n\nfrom ..common.util import helper\n\nLIMIT = 2\n',
    )
    with pytest.raises(InlineError, match="'LIMIT' is defined differently"):
        render_complete(root / "agents" / "one.py", root)


def test_conflicting_import_bindings_are_rejected(tmp_path: Path):
    # `import datetime` vs `from datetime import datetime` shadow each other once flattened.
    root = tmp_path / "pkg"
    _write(
        root / "common" / "util.py",
        '"""util"""\n\nimport datetime\n\ndef now():\n    return datetime.datetime.now()\n',
    )
    _write(
        root / "agents" / "one.py",
        '#!/usr/bin/env python3\n"""one"""\n\nfrom datetime import datetime\n\n'
        "from ..common.util import now\n\nSTAMP = datetime.now\n",
    )
    with pytest.raises(InlineError, match="'datetime' is bound differently"):
        render_complete(root / "agents" / "one.py", root)


def test_identical_import_bindings_are_allowed(tmp_path: Path):
    root = tmp_path / "pkg"
    _write(
        root / "common" / "util.py",
        '"""util"""\n\nfrom pathlib import Path\n\nHOME = Path.home\n',
    )
    _write(
        root / "agents" / "one.py",
        '#!/usr/bin/env python3\n"""one"""\n\nfrom pathlib import Path\n\n'
        "from ..common.util import HOME\n\nCWD = Path.cwd\n",
    )
    assert "from pathlib import Path" in render_complete(root / "agents" / "one.py", root)
