# Cline 書式サンプル

Cline が読んで初めて意味を持つファイルの最小サンプル。仕組みの説明は知識スキル側にあり、ここには置かない。違いのまとめは [../../docs/differences/cline.md](../../docs/differences/cline.md)。

| サンプル                                                               | Cline での本来の置き場所                                                                                                                                                                                                               | 正本の知識スキル                             |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| [skill/cline-sample-skill/SKILL.md](skill/cline-sample-skill/SKILL.md) | `.cline/skills/<name>/SKILL.md`（推奨。`.clinerules/skills/`・`.claude/skills/` も可）／`~/.cline/skills/<name>/SKILL.md`                                                                                                              | cline-skill-writer（`skills-reference.md`）  |
| [rule/src.example.md](rule/src.example.md)                             | `.clinerules/<name>.md`。`paths:` frontmatter は `tools/agents-rules` が出す `.clinerules/agents-*.md` と同じ形                                                                                                                        | cline-rule-writer                            |
| [personal-info/](personal-info/README.md)                              | プラグイン（`package.json` の `cline.plugins` ＋ `AgentPlugin` を export する `index.ts`）。`cline plugin install ... --cwd .` で `.cline/plugins/` に入る。`docs/integrations/justfile` の `cline-personal-info` が使うので移動しない | cline-plugin-writer（`plugin-reference.md`） |

- `AGENTS.md` は Cline でも frontmatter なしの素の Markdown なので、サンプルは置かない。Memory Bank（`memory-bank/`）は書式ではなく運用手法なので知識スキル（cline-memory）に任せる。
- このリポジトリの `.cline/skills/` は `just agent-compat-sync` が ai-tools-knowledge から作る gitignore 済みのコピーで、サンプルではない。
