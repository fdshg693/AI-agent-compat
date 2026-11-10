# Cursor 書式サンプル

Cursor が読んで初めて意味を持つファイルの最小サンプル。仕組みの説明は知識スキル側にあり、ここには置かない。違いのまとめは [../../docs/differences/cursor.md](../../docs/differences/cursor.md)。

| サンプル                                                                 | Cursor での本来の置き場所                                                                              | 正本の知識スキル                                                                          |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| [skill/cursor-sample-skill/SKILL.md](skill/cursor-sample-skill/SKILL.md) | `.cursor/skills/<name>/SKILL.md` または `.agents/skills/<name>/SKILL.md`                               | cursor-skill-use（`reference.md`）                                                        |
| [plugin/.cursor-plugin/plugin.json](plugin/.cursor-plugin/plugin.json)   | プラグインルートの `.cursor-plugin/plugin.json`（旧 `cursor-plugins/meta` のもの。必須は `name` のみ） | cursor-plugin-use                                                                         |
| [rule/rule.example.mdc](rule/rule.example.mdc)                           | `.cursor/rules/<name>.mdc`（拡張子は `.mdc` 必須）。frontmatter は `tools/agents-rules` の出力と同じ形 | cursor-memory（`memory.md`）                                                              |
| [hooks/hooks.json](hooks/hooks.json)                                     | `.cursor/hooks.json`（プロジェクト）／`~/.cursor/hooks.json`（ユーザー）                               | cursor-sdk-use（`references/hooks.md`）                                                   |
| [agent/security-auditor.md](agent/security-auditor.md)                   | `.cursor/agents/<name>.md`                                                                             | cursor-cli-use（`memos/05-reusable-agents-pointer.md`）、cursor-sdk-use（`subagents.md`） |

- 実際に配っている Cursor 用マニフェストは `skills/plugins/ai-tools-knowledge/.cursor-plugin/plugin.json`。
- `AGENTS.md`／`CLAUDE.md` は Cursor でも frontmatter なしの素の Markdown なので、サンプルは置かない。
