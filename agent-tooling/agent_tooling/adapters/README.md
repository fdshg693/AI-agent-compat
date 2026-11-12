# Hook Adapters

`adapters/` contains one renderer per supported agent and scenario. The
`nested_agents_md` renderers preserve the existing AGENTS model and the
`scoped_rules` renderers consume the common `MatchedRule` model. Neither kind
of renderer discovers the other scenario's inputs. The `agent_sessions`
renderers only create/update/delete entries in the session registry
(`agent_tooling/core/sessions.py`); they inject no context.

The `MatchedRule` model preserves the Rule path, matched `paths` pattern,
concrete touched file, Rule content, and scenario ID. Renderers only adapt
that model to the agent's event/output contract.

| Agent       | AGENTS target / artifact                                                                             | Rule target / artifact                                                                       | Session target / artifact                                                                        |
| ----------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Claude      | `adapters/claude/nested_agents_md.py` / `hooks/generated/claude/nested_agents_md.py`                 | `adapters/claude/scoped_rules.py` / `hooks/generated/claude/scoped_rules.py`                 | `adapters/claude/agent_sessions.py` / `hooks/generated/claude/agent_sessions.py`                 |
| Codex       | `adapters/codex/nested_agents_md.py` / `hooks/generated/codex/nested_agents_md.py`                   | `adapters/codex/scoped_rules.py` / `hooks/generated/codex/scoped_rules.py`                   | `adapters/codex/agent_sessions.py` / `hooks/generated/codex/agent_sessions.py`                   |
| Cursor      | `adapters/cursor/nested_agents_md.py` / `hooks/generated/cursor/nested_agents_md.py`                 | `adapters/cursor/scoped_rules.py` / `hooks/generated/cursor/scoped_rules.py`                 | `adapters/cursor/agent_sessions.py` / `hooks/generated/cursor/agent_sessions.py`                 |
| Antigravity | `adapters/antigravity/nested_agents_md.py` / `hooks/generated/antigravity/nested_agents_md.py`       | `adapters/antigravity/scoped_rules.py` / `hooks/generated/antigravity/scoped_rules.py`       | `adapters/antigravity/agent_sessions.py` / `hooks/generated/antigravity/agent_sessions.py`       |
| Kilo        | `adapters/kilo/nested_agents_md.py` and `.ts` / `hooks/generated/kilo/nested_agents_md.py` and `.ts` | `adapters/kilo/scoped_rules.py` and `.ts` / `hooks/generated/kilo/scoped_rules.py` and `.ts` | `adapters/kilo/agent_sessions.py` and `.ts` / `hooks/generated/kilo/agent_sessions.py` and `.ts` |

Claude also has Claude-only hooks with no counterpart in other agents
(formerly `.claude/hooks/*.py`): `adapters/claude/<hook id>.py` for
`block_large_read`, `inject_env_vars`, `long_run_collector`,
`long_run_statement_collector`, `stop_alert`, `task_tracker_session`,
`summarize_read`, `summarize_webfetch`, `translate_prompt`, `recommend_skills`,
`skill_usage_tracker` and `skill_enquete_stop`, each built to
`hooks/generated/claude/<hook id>.py`. Their shared helpers live in
`adapters/claude/common/` and must be imported as functions
(`from .common.runtime import init_hook_context`), because the builder
flattens every inlined module into one namespace. Paths follow
`common/paths.py`: the hook's own `config/`, `.env`, `state/` and `logs/` sit
next to the installed file (`hook_dir()`), and project content is resolved
with `resolve_project_dir(payload)`.
`stop_alert` takes its sound and popup backends from `agent_tooling/notify/`
(per-OS dispatch: Windows popup, macOS Notification Center; no environment or
`.env` reads); the adapter resolves `STOP_ALERT_*`, `.env`, `alert.wav` and the
macOS helper `.app` location and passes the values in.

The `notify` scenario (`adapters/<agent>/notify.py`, built to
`hooks/generated/<agent>/notify.py`; Claude, Codex and Kilo, where Kilo
also has a `notify.ts` sidecar) posts a per-session notification when the agent needs the user and
removes it once the user responds. One artifact branches on the event name;
the adapter decides which events post or remove and what the text says, while
`agent_tooling/notify/` (`notify_post` / `notify_remove` / `format_title`)
does the posting, removing and formatting. It overlaps `stop_alert` on
Claude's Stop, so install only one of the two.

`stop_alert` is the one Claude-only hook that also has a Kilo port:
`adapters/kilo/stop_alert.ts` listens for `session.idle` (skipping subagent
sessions that have a `parentID`) and spawns, without waiting,
`adapters/kilo/stop_alert.py`, which uses the same `agent_tooling/notify/`
sound and popup backends as the Claude hook (plus the Claude `common/` log and
`.env` helpers via absolute `agent_tooling.adapters.claude.common.*` imports).
It overlaps the Kilo adapter of `notify`, so install only one of the two.
Both are built to `hooks/generated/kilo/stop_alert.*`.

The build manifest owns this agent x scenario mapping. Existing AGENTS targets
remain independently buildable while Rule and session targets are added
alongside them. Edit scenario and target sources first; the builder then
produces the matching generated artifacts.
