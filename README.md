# agent-compat/

このリポジトリを Claude Code 以外の AI コーディングツール（Codex・GitHub Copilot・Cursor・Antigravity・Cline・Kilo Code）でも使えるようにする仕組みと、その資料を置く。スキルの実体は置かない（スキルは `skills/plugins/` と `tools/_plugin/` に Claude Code スキルとして 1 か所だけ置く）。

## 中身

- [agent-tooling/](agent-tooling/README.md) — 複数ツール向けのフックとコンテキスト注入。フックの正本はここで、`.claude/hooks/` などはインストール先（[hook-distribution](../maintenance/docs/hook-distribution.md)）
- [formats/](formats/) — ツール固有の書式でしか書けないファイルの最小サンプル（`formats/<tool>/` の `skill`・`plugin`・`rule`・`memory` 等）。各ツールの README が、対応する置き場所と根拠の知識スキルを示す
- [docs/differences/](docs/differences/index.md) — Claude Code を基準にした、ツールごとの書き方の相違点

## 他ツールへスキルを届ける方法

`registry/ai-tools.yaml` で宣言し、`maintenance/scripts/plugin_meta/generate/` の生成器が作る（詳細は [ai-tools-config](../maintenance/docs/ai-tools-config.md)）。

| ツール                        | 方法                                                                                                                                                                              |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Codex・GitHub Copilot         | `skills/plugins/ai-tools-knowledge` に各ツールのマニフェストを同梱し、生成したマーケットプレイス（`.agents/plugins/marketplace.json`・`.github/plugin/marketplace.json`）から指す |
| Cursor                        | 同じプラグインに `.cursor-plugin/plugin.json` を同梱する                                                                                                                          |
| Cline・Kilo Code・Antigravity | ワークスペース直下からしか読まないので、`just agent-compat-sync` で gitignore 済みのコピー（`.cline/skills/`・`.kilo/skills/`・`_agents/plugins/antigravity-meta/`）を作る        |

AGENTS.md から各ツールのルールを作るのは [tools/agents-rules](../tools/agents-rules/README.md)（手動実行）。
