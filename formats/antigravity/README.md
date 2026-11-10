# Antigravity 書式サンプル

Google Antigravity（IDE と `agy` CLI）が読んで初めて意味を持つファイルの最小サンプル。仕組みの説明は知識スキル側にある。違いのまとめは [../../docs/differences/antigravity.md](../../docs/differences/antigravity.md)。

| サンプル                                                                           | Antigravity での本来の置き場所                                                                                                         | 正本の知識スキル                                                 |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| [skill/antigravity-sample-skill/SKILL.md](skill/antigravity-sample-skill/SKILL.md) | `.agents/skills/<name>/SKILL.md`（グローバルは `~/.gemini/config/skills/<name>/`）                                                     | antigravity-skills                                               |
| [plugin/plugin.json](plugin/plugin.json)                                           | プラグインルート直下の `plugin.json`（ドットフォルダなし）。置き場所は `.agents/plugins/<name>/` か `~/.gemini/config/plugins/<name>/` | antigravity-skills（プラグイン節）、agy-cli-docs（`agy plugin`） |
| [rule/src.example.md](rule/src.example.md)                                         | `.agents/rules/<name>.md`。frontmatter は `tools/agents-rules` の出力と同じ形                                                          | antigravity-memory                                               |
| [agent/code-auditor.md](agent/code-auditor.md)                                     | `.agents/agents/<name>.md` または `.agents/agents/<name>/agent.md`                                                                     | antigravity-subagents                                            |

- `GEMINI.md`／`AGENTS.md` は frontmatter なしの素の Markdown なので、サンプルは置かない。
- hooks（プラグインが `hooks.json` を同梱できる）は書式を知識スキルで確認できていないため、サンプルは置かない。
- このリポジトリの `_agents/plugins/antigravity-meta/` は生成された gitignore 済みのコピーで、サンプルではない。
