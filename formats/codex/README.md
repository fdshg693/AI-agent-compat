# Codex 書式サンプル

Codex が読んで初めて意味を持つファイルの最小サンプル。仕組みの説明は知識スキル側にあり、ここには置かない。違いのまとめは [../../docs/differences/codex.md](../../docs/differences/codex.md)。

| サンプル                                                                                   | Codex での本来の置き場所                                                                                                                                   | 正本の知識スキル                                     |
| ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| [skill/codex-sample-skill/SKILL.md](skill/codex-sample-skill/SKILL.md)                     | `.agents/skills/<name>/SKILL.md`（リポジトリ）／`~/.agents/skills/<name>/SKILL.md`（ユーザー）。frontmatter は `name`・`description` のみ                  | codex-skill-authoring                                |
| [skill/codex-sample-skill/agents/openai.yaml](skill/codex-sample-skill/agents/openai.yaml) | スキル内の `agents/openai.yaml`（任意。UI 表示・暗黙起動ポリシー・ツール依存）                                                                             | codex-skill-authoring                                |
| [plugin/.codex-plugin/plugin.json](plugin/.codex-plugin/plugin.json)                       | プラグインルートの `.codex-plugin/plugin.json`（旧 `codex-plugins/meta` のもの）                                                                           | codex-skill-authoring、codex-docs（`build-plugins`） |
| [plugin/marketplace.json](plugin/marketplace.json)                                         | `.agents/plugins/marketplace.json`（リポジトリ）／`~/.agents/plugins/marketplace.json`（個人）。プラグインルートではなくマーケットプレイスのルート側に置く | codex-docs（`build-plugins`）                        |
| [rule/default.rules](rule/default.rules)                                                   | `~/.codex/rules/*.rules`／`.codex/rules/*.rules`。指示ではなくコマンド実行の許可ルール（execpolicy）                                                       | codex-settings                                       |

- 実際に配っている Codex 用マニフェストは `skills/plugins/ai-tools-knowledge/.codex-plugin/plugin.json`。`agents/openai.yaml` の実例は同プラグインの `skills/codex-*/agents/openai.yaml`。
- `AGENTS.md` は Codex でも frontmatter なしの素の Markdown なので、サンプルは置かない（違いはファイル名と読み込み範囲だけ。codex-memory を参照）。
- hooks の `hooks.json` は Claude Code とほぼ同じ形なのでサンプルは置かない（違いは codex-hooks を参照）。
