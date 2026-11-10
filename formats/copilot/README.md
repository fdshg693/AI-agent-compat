# GitHub Copilot 書式サンプル

GitHub Copilot（Copilot CLI・VS Code・Copilot cloud agent）が読んで初めて意味を持つファイルの最小サンプル。仕組みの説明は知識スキル側にあり、ここには置かない。違いのまとめは [../../docs/differences/copilot.md](../../docs/differences/copilot.md)。

| サンプル                                                                             | Copilot での本来の置き場所                                                                                                                               | 正本の知識スキル                                         |
| ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| [skill/copilot-sample-skill/SKILL.md](skill/copilot-sample-skill/SKILL.md)           | `.github/skills/<name>/SKILL.md`（`.claude/skills/`・`.agents/skills/` も可）。frontmatter は `name`・`description`（任意で `license`・`allowed-tools`） | copilot-writing-skills（スキル名 `writing-skills`）      |
| [plugin/plugin.json](plugin/plugin.json)                                             | プラグインルートの `plugin.json`（必須は `name` のみ）。`.plugin/`・`.github/plugin/`・`.claude-plugin/` 配下も検出される                                | copilot-writing-plugins（`references/create-plugin.md`） |
| [plugin/marketplace.json](plugin/marketplace.json)                                   | マーケットプレイスのリポジトリの `.github/plugin/marketplace.json`（`.claude-plugin/marketplace.json` も検出対象）                                       | copilot-writing-plugins（`references/marketplace.md`）   |
| [rule/typescript.instructions.example.md](rule/typescript.instructions.example.md)   | `.github/instructions/<name>.instructions.md`（`applyTo` に glob）                                                                                       | writing-copilot-instructions                             |
| [memory/copilot-instructions.example.md](memory/copilot-instructions.example.md)     | `.github/copilot-instructions.md`（リポジトリ全体に常時適用）                                                                                            | writing-copilot-instructions                             |
| [agent/security-reviewer.agent.example.md](agent/security-reviewer.agent.example.md) | プラグイン内の `agents/<name>.agent.md`                                                                                                                  | copilot-writing-plugins（`references/components.md`）    |

- ファイル名の `.example` は、このリポジトリで本物の指示として読まれないように付けたもの。本来の名前は右列のとおり。
- 実際に配っている Copilot 用マニフェストは `skills/plugins/ai-tools-knowledge/plugin.json`。
- `AGENTS.md` は Copilot でも素の Markdown なので、サンプルは置かない。
- hooks は知識スキルに書式の詳細がない（置き場所はプラグインルートの `hooks.json`）ので、サンプルは置かない。
