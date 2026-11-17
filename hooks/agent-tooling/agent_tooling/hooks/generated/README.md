# Generated Hook Outputs

This directory contains tracked, distributable hook artifacts produced by
`agent_tooling/hooks/build/build.py`. Each agent may have a `nested_agents_md`
artifact for AGENTS injection, a `scoped_rules` artifact for Claude Rules, and
an `agent_sessions` artifact that registers the session in the per-user
registry. `claude/` additionally holds the Claude-only hooks (formerly kept in
`.claude/hooks/*.py`), one self-contained file per hook id. Do not edit files here by hand. Change the common model, scenario,
or agent target and rebuild instead.

The build manifest is the complete output set. A build removes stale files
under `generated/` that are not listed in that manifest, so an artifact is
valid only when it can be reproduced from source and target inputs.

The generated Python files must be self-contained with respect to the package:
stdlib imports may remain, but relative and `agent_tooling.*` imports must be inlined.
Third-party imports may remain only when the entry declares them: PEP 723
`dependencies` (the block is kept right after the shebang, before the
docstring; run with `uv run --script`) or `project_imports` for a
`runner: uv-project` hook. Kilo's TypeScript sidecars are copied from each
scenario target as part of the same build.

## `catalog.json`

`catalog.json` aggregates every `scenarios/<id>/hook.yaml` together with the
build's file list. Installers such as `skill-tools hooks` read it (located via
the repository's `repo-hooks.yaml`) instead of walking this tree.

- `hooks[]`: `id`, `description`, `distributable`, `requiresTools`, `agents`.
- `agents.<agent>`: `runner` (`python` / `uv-script` / `uv-project`), `main`
  (the `installPath` that is registered or, for Kilo, the TS plugin),
  `files[]` and `seedFiles[]` (`path` relative to this directory,
  `installPath` relative to the install directory), `dependencies` (PEP 723),
  and `registrations[]` (event, matcher and tool-specific options, never a
  command string: the installer builds it from where it placed `main`).

Seed files are configuration templates copied to
`<agent>/seed/<hook id>/`. An installer places them only when the destination
does not exist yet.
