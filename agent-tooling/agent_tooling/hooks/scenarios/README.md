# Hook Scenarios

`scenarios/` contains independent hook behaviors, not agent-specific adapters
or generated scripts. Each behavior gets exactly one directory under this
folder. The existing `nested_agents_md/` scenario continues to read and inject
`AGENTS.md`; the `scoped_rules/` scenario reads Claude Rules; the
`agent_sessions/` scenario writes/removes session entries in the registry and
injects nothing.

Every scenario also has a `hook.yaml` (distribution and registration
metadata, see `../AGENTS.md`). Claude-only hooks such as `block_large_read`
or `stop_alert` are scenarios too, but their directory holds only
`hook.yaml` and optional seed templates (e.g. `inject_env_vars.yaml`): the
behavior lives entirely in `adapters/claude/<id>.py`.

Each scenario definition (the Python-backed scenarios above) declares:

- `SCENARIO_ID`: stable identifier used by the common model.
- `RULES_DIRECTORY`: repository-relative Claude Rule root.
- `REQUIRE_PATHS`: whether Rule frontmatter must contain `paths`.
- `FILE_REGEXES`: optional Python `re` expressions applied after Rule glob
  matching.

Only the `scoped_rules` scenario uses the Rule fields above. Rule `paths`
values are Claude Rule glob/file patterns and must not contain scenario-specific
regular expressions. The builder matches each expression with `re.fullmatch`
against a repository-relative POSIX path. Anchors are therefore optional,
`re.search` is not used, an empty tuple disables the extra filter, and multiple
expressions are combined with AND semantics. Invalid expressions fail
validation.

The scoped-rules discovery reads only concrete touched paths supplied by an
agent target, so a matching Rule can apply to a not-yet-existing Add File path.
Its session cache is independent from nested AGENTS discovery and keys emitted
content by scenario, Rule path, and body fingerprint.

The `agent_sessions/` scenario declares `SCENARIO_ID = "agent_sessions"`, the
normalized actions `start`/`end`/`cwd`/`heartbeat`, and the entry fields
(`schema`/`agent`/`session_id`/`pid`/`pid_source`/`cwd`/`started_at`/
`last_seen`/`hook_event`). `registry.apply_event` maps an event to
`agent_tooling/core/sessions.py` and is fail-open. Only `start` creates a file;
`cwd`/`heartbeat` update an existing file; `end` removes it. The `pid_source`
(`agent`/`host`/`unknown`) decides whether liveness is PID-based or falls back
to the `last_seen` grace window.
