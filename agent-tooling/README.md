# Agent Tooling

Portable Python package for agent context discovery and cross-tool hook
artifacts. The package keeps filesystem-oriented context sources separate from
AI-tool-specific input and output adapters.

## Layout

- `agent_tooling/core/` contains tool-independent path normalization, command
  parsing, and other side-effect-free helpers.
- `agent_tooling/adapters/` contains Codex, Claude, Cursor, Antigravity, and
  Kilo event/payload adapters.
- `agent_tooling/sources/` holds the stateless context source collectors used
  by the context check: applicable `AGENTS.md` files and scoped Claude Rules.
- `agent_tooling/checks/` holds the advisory coverage check that reads the
  staged Git index and builds the report rendered by `agent-context-check`.
- `agent_tooling/hooks/` contains the independent hook scenarios, the builder,
  and tracked generated artifacts.
- `tests/` contains unit tests that do not start an agent application.

`nested_agents_md` reads only `AGENTS.md` candidates. `scoped_rules` reads only
`.claude/rules/**/*.md` files. `agent_sessions` reads no files: it registers
run/end/CWD in the per-user session registry. These are independent input
contracts.

## Install From A Checkout

From a checkout:

```text
uv tool install --editable agent-tooling
```

For an installed or packaged copy, install the package with your Python tool
manager and invoke the command directly:

```text
uv tool install agent-tooling
agent-context-check --staged
```

For a locally built wheel, pass its path instead, for example
`uv tool install /path/to/agent_tooling-0.1.0-py3-none-any.whl`.

When using this repository's checkout, prefer `uv run --project agent-tooling`
so the command resolves against the workspace package without a global install.

The generated hook artifacts are distributable package data. They are
installed and registered by `skill-tools hooks install`, which reads
`agent_tooling/hooks/generated/catalog.json` through the repository-root
`repo-hooks.yaml` (see `maintenance/docs/hook-distribution.md`). Generated files
are not hand-edited.

## Commands

| Command               | Purpose                                                                             | Entry module                    |
| --------------------- | ----------------------------------------------------------------------------------- | ------------------------------- |
| `agent-context-check` | Advisory list of context sources for staged changes or one explicitly selected file | `agent_tooling/cli.py`          |
| `agent-sessions`      | List the per-user registry of live AI agent sessions (or watch it)                  | `agent_tooling/sessions_cli.py` |

## Agent Sessions

The `agent_sessions` hook scenario registers AI agent sessions in a per-user
registry, and `agent-sessions` lists them.

```text
uv run --project agent-tooling agent-sessions
uv run --project agent-tooling agent-sessions --all
uv run --project agent-tooling agent-sessions --prune
uv run --project agent-tooling agent-sessions --json
uv run --project agent-tooling agent-sessions --agent claude
```

After installing the package, the equivalent command is `agent-sessions`. The
default view lists live sessions only; stale (crashed) entries appear with
`--all` and are removed only when `--prune` is given. `--json` emits a stable
structure, and `--prune --json` wraps it as
`{ "sessions": [...], "pruned": N }`. Without `--watch`, the command prints one
snapshot and exits.

Every run also collapses PID-reuse duplicates: when a session's `end` never
arrives (interrupt, crash) and its process is replaced or its PID reused, older
entries keep the same PID and still look live. Entries that share a positive
PID are reduced to the one with the newest `last_seen`; snapshot runs report the
removed count on stderr. This applies to every PID source, including the shared
Kilo `host` PID. The cleanup lives in the CLI only; the hooks never perform it.

### Persistent view (`--watch`)

`--watch` (or `-w`) keeps the process alive and refreshes the view every
`--interval` seconds (default `3`) until interrupted with `Ctrl-C`:

```text
uv run --project agent-tooling agent-sessions --watch
uv run --project agent-tooling agent-sessions --watch --interval 1
uv run --project agent-tooling agent-sessions --watch --json
uv run --project agent-tooling agent-sessions --watch --all --prune
```

The output depends on where it is written:

- On a terminal (TTY), the same screen is redrawn in place with ANSI escapes.
- In a pipe or redirect, frames are appended without control characters, so
  logs stay readable.
- With `--json`, each refresh is one compact JSON record per line (NDJSON).
- `--prune` runs once per refresh and the removed count appears in the frame
  (or the NDJSON record), not on stderr.
- If the downstream consumer stops early (`--watch --json | head`), the command
  exits without a traceback.

### Environment variables

| Variable             | Purpose                                                        | Default                                                                                                                                        |
| -------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `AGENT_SESSIONS_DIR` | Registry directory                                             | `%TEMP%\agent-sessions` on Windows; `$XDG_RUNTIME_DIR/agent-sessions`, `$XDG_CACHE_HOME/agent-sessions`, or `~/.cache/agent-sessions` on POSIX |
| `AGENT_SESSIONS_TTL` | Live window in seconds for entries whose PID source is unknown | `43200` (12 hours)                                                                                                                             |

Liveness is PID-based; entries whose PID source is unknown fall back to the
`last_seen` window set by `AGENT_SESSIONS_TTL`.

## Development

```text
just --justfile agent-tooling/justfile generate
just --justfile agent-tooling/justfile generate-check
just --justfile agent-tooling/justfile rules-check
just --justfile agent-tooling/justfile test
```

The existing hook regeneration job is intentionally the only automatic hook
job. Context checks are advisory commands and are not registered in
`lefthook.yml`.

## Context Check

After staging a commit, inspect the context sources that may need review:

```text
uv run --project agent-tooling agent-context-check --staged
uv run --project agent-tooling agent-context-check --staged --format json
```

After installing the package, the equivalent command is
`agent-context-check --staged`. Changed paths come only from the Git index;
unstaged and untracked paths are intentionally excluded. Listed context source
files are read from the working tree so their current contents can be reviewed.
The command reports candidates, not required updates: read each listed
`AGENTS.md` or Claude Rule and decide
whether the implementation has diverged from it. The command exits successfully
when candidates exist or do not exist. Git errors and malformed Claude Rule
frontmatter are reported on stderr with a non-zero exit code.

In an external project, use any applicable `AGENTS.md` immediately as project
guidance. If the project has no `.claude/rules/` directory, the Claude Rule
source is simply empty; no placeholder Rule is needed.

Claude Rules with a `paths` frontmatter list are matched using the same
repository-relative POSIX glob semantics as the hooks. A Rule with no `paths`
key is reported once as `always`; an empty or malformed `paths` value is an
error. `AGENTS.override.md` takes precedence over `AGENTS.md` in the same
directory.

### Explain a file path

Use `explain` to inspect context candidates for a file without staging it:

```text
uv run --project agent-tooling agent-context-check explain src/app.py
uv run --project agent-tooling agent-context-check explain C:/work/project/src/app.py --format json
```

Relative paths are resolved from the invocation directory and reported relative
to the discovered Git root. Absolute paths are also accepted. The command works
for unstaged files and files that do not exist yet, but rejects directories,
paths outside the repository, and symlinks that resolve outside it. External
symlink targets under `.claude/rules/` are also rejected before their contents
are read. Git is used to discover the repository root; invoking from outside a
Git worktree is an error. The report gives the source path, scope, and matching
reason for each candidate. It is advisory only: it does not reproduce a
specific AI tool's injection order, precedence, or final prompt. The existing
`--staged` mode and its JSON shape are unchanged.
