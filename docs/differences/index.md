# Claude Code との書き方の相違点

Claude Code を基準に、他の AI コーディングツールで書き方が変わる点だけをまとめた OKF の概念ドキュメント群。仕組みの詳しい説明は `skills/plugins/ai-tools-knowledge/` の知識スキルにあり、各ドキュメントはそこを根拠にしている。ツール固有の書式の実物は [formats/](../../formats/) にある。知識スキルで確かめられなかった点は各ドキュメントで「未確認」と書いている。

## ドキュメント

- [codex](codex.md) — OpenAI Codex
- [copilot](copilot.md) — GitHub Copilot（Copilot CLI・VS Code・cloud agent）
- [cursor](cursor.md) — Cursor（エディタと `agent` CLI）
- [antigravity](antigravity.md) — Google Antigravity（IDE と `agy` CLI）
- [cline](cline.md) — Cline
- [kilo](kilo.md) — Kilo Code

## 一覧

| 観点                     | Codex                                                                      | GitHub Copilot                                                      | Cursor                                                                 | Antigravity                                                       | Cline                                                              | Kilo Code                                                                    |
| ------------------------ | -------------------------------------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| スキルの置き場所         | `.agents/skills/<name>/`（起動ディレクトリ〜ルート）、`~/.agents/skills/`  | `.github/skills/<name>/`（`.claude/skills`・`.agents/skills` も可） | `.cursor/skills/`・`.agents/skills/`。`.claude/skills/` も読む         | `.agents/skills/`。グローバルは `~/.gemini/config/skills/`        | `.cline/skills/`（推奨）・`.clinerules/skills/`・`.claude/skills/` | `.kilo/skills/`。互換で `.agents/`・`.claude/skills/`                        |
| スキルの frontmatter     | `name`・`description` のみ。起動制御は `agents/openai.yaml`                | `name`・`description` 必須。任意で `license`・`allowed-tools`       | `name`・`description`・`paths`・`disable-model-invocation`・`metadata` | `name`（任意）と `description` だけ                               | 公式は `name`・`description` のみ                                  | `name`・`description` 必須。`license`・`compatibility`・`metadata` 任意      |
| 明示的な呼び出し         | `$skill-name` または `/skills`                                             | 未確認                                                              | 未確認                                                                 | 未確認                                                            | 未確認                                                             | 未確認                                                                       |
| プラグインのマニフェスト | `.codex-plugin/plugin.json`。パスは `./` 始まり                            | ルートの `plugin.json`（必須は `name`）                             | `.cursor-plugin/plugin.json`（必須は `name`）                          | ルートの `plugin.json`（`{ "name" }`）                            | `package.json` の `cline.plugins` と AgentPlugin（TS）             | `.kilo/plugin/` の TS を自動検出。パッケージは `exports`・`engines.opencode` |
| マーケットプレイス       | `.agents/plugins/marketplace.json`（`.claude-plugin/` も互換で読む）       | `.github/plugin/marketplace.json`。`enabledPlugins` で有効化        | `.cursor-plugin/marketplace.json` と公式審査。書式は未確認             | `agy plugin install x@mp`。定義ファイルの書式は未確認             | 記載なし。`cline plugin install` で git・npm・ローカルから入れる   | 公式 Marketplace あり。定義ファイルの書式は未確認                            |
| ルール                   | 指示ルールは無い。`.codex/rules/*.rules` はコマンド許可（execpolicy）      | `.github/instructions/*.instructions.md`（`applyTo` に glob）       | `.cursor/rules/*.mdc`（`alwaysApply`・`description`・`globs`）         | `.agents/rules/*.md`（`trigger` 4 種）。glob のキー名は未確定     | `.clinerules/*.md`（`paths:` で条件付き）                          | frontmatter なしの Markdown。`kilo.jsonc` の `instructions` で読む           |
| メモリファイル           | `AGENTS.md`／`AGENTS.override.md`。開始時に 1 回、ルート〜起動ディレクトリ | `.github/copilot-instructions.md` と `AGENTS.md`（近いもの優先）    | `AGENTS.md`（ネストは結合）。`CLAUDE.md` も読む                        | ルートの `GEMINI.md`・`AGENTS.md`、`~/.gemini/GEMINI.md`          | ルートの `AGENTS.md` と `~/.agents/AGENTS.md`。ネストは未確認      | `AGENTS.md`（互換で `CLAUDE.md`）。ネストは Read 時に読み込む                |
| フック                   | `.codex/hooks.json` か `[hooks]`。`/hooks` で信頼するまで動かない          | プラグインはルートの `hooks.json`。中身の書式は未確認               | `.cursor/hooks.json`（`version: 1`）。exit 2 で拒否                    | プラグインが `hooks.json` を同梱できる。書式は未確認              | プラグインの hooks（`beforeTool` 等）。`.cline/hooks/` は未確認    | プラグインの hooks（`tool.execute.before` 等）                               |
| サブエージェント         | 定義ファイルの書式は未確認                                                 | `agents/<name>.agent.md`（frontmatter に `tools`）                  | `.cursor/agents/*.md`（`model`・`readonly`・`is_background`）          | `.agents/agents/<name>.md`（`tools`・`model` 等、ネスト 10 階層） | 組み込みの `use_subagents` だけ。自作定義は未確認                  | `.kilo/agents/*.md`（`mode: primary/subagent/all`、`permission`）            |

Claude Code 固有の `allowed-tools`（Copilot を除く）、`` !`command` `` による動的コンテキスト注入、このリポジトリ独自の `meta:` ブロックは、どのツールでも同じ動きにはならない（[claude-code-first-skills](../../../maintenance/docs/claude-code-first-skills.md)）。
