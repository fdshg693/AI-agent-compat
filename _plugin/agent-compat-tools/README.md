# agent-compat-tools

[`agent-compat/`](../../) 配下の CLI を、会話の中から判断付きで使うためのスキルを集めた Claude Code プラグイン。[`tools/_plugin/my-tools`](../../../tools/_plugin/my-tools/) と同じ形で、ツール本体は同梱しない。各スキルは、対応する CLI が別途インストール済みであることを前提にする。

## 収録スキル

| スキル                                           | 対象 CLI                                                            | インストール                                                                        |
| ------------------------------------------------ | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| [agent-logs-cli](skills/agent-logs-cli/SKILL.md) | [`agent-logs`](../../logs/agent-logs/README.md)（ログの検索・集計） | `uv tool install --editable agent-compat/logs/agent-logs`（アンブレラのルートから） |

一覧は生成カタログ [skills/CATALOG.md](skills/CATALOG.md) も見る。各スキルの設計意図は同階層の `README.md`、実行時の手順は `SKILL.md`。

## 役割分担

- スキルは使い方と判断だけを扱い、インストールは行わない（[tool-companion-skills](../../../maintenance/docs/tool-companion-skills.md)）。
- 各ツールのログ形式など仕様の正本は知識スキル（`skills/plugins/ai-tools-knowledge/`・`skills/plugins/cc-knowledge/`）にあり、ここには重複させない。
- agent-compat に CLI が増えたら、別プラグインを作らずこのプラグインにスキルを足す。
