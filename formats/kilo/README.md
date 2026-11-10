# Kilo Code 書式サンプル

Kilo Code が読んで初めて意味を持つファイルの最小サンプル。仕組みの説明は知識スキル側にあり、ここには置かない。違いのまとめは [../../docs/differences/kilo.md](../../docs/differences/kilo.md)。

| サンプル                                                             | Kilo での本来の置き場所                                                                                         | 正本の知識スキル                                       |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| [skill/kilo-sample-skill/SKILL.md](skill/kilo-sample-skill/SKILL.md) | `.kilo/skills/<name>/SKILL.md`／`~/.kilo/skills/<name>/SKILL.md`（`.agents/skills/`・`.claude/skills/` も読む） | kilo-skill-guide、kilo-code-docs（`customize/skills`） |
| [rule/formatting.example.md](rule/formatting.example.md)             | `.kilo/rules/formatting.md`（frontmatter なしの Markdown）                                                      | kilo-memory-guide（`instructions.md`）                 |
| [rule/kilo.example.jsonc](rule/kilo.example.jsonc)                   | プロジェクトの `kilo.jsonc` の `instructions`（グローバルは `~/.config/kilo/kilo.jsonc`）                       | kilo-memory-guide（`instructions.md`）                 |
| [agent/code-reviewer.example.md](agent/code-reviewer.example.md)     | `.kilo/agents/code-reviewer.md`（ファイル名から `.md` を除いたものが agent 名。`.example` は付けない）          | kilo-agent-writer（`subagents.md`・`modes.md`）        |
| [plugin/env-guard.ts](plugin/env-guard.ts)                           | `.kilo/plugin/env-guard.ts`（置くだけで自動検出）／`~/.config/kilo/plugin/`                                     | kilo-plugin-writer（`plugin-reference.md`）            |

- 実際に動いているプラグインの例は、このリポジトリの `.kilo/plugin/agent_sessions.ts`（agent-tooling のフック出力。TS から Python を起動する）。
- `AGENTS.md` は Kilo でも frontmatter なしの素の Markdown なので、サンプルは置かない。
- このリポジトリの `.kilo/skills/` は `just agent-compat-sync` が ai-tools-knowledge から作る gitignore 済みのコピーで、サンプルではない。
