# agent-logs-cli スキルについて

[`agent-compat/logs/agent-logs/`](../../../../logs/agent-logs/README.md) の `agent-logs` CLI を、Claude が会話の中から使えるようにするためのスキル。このファイルは人間のメンテナ向けで、Claude が実行時に読むのは [SKILL.md](SKILL.md)。

## なぜこのスキルがあるか

- サブコマンドとフラグは `--help` で分かるが、「どの順で使うか」「欠けた値（`null`）をどう読むか」「出力を外へ出してよいか」は `--help` に書けない。スキルはこの判断だけを持つ。
- ツールごとにトークン・コスト・本文の有無が違い、知らずに `stats` を比べると誤った結論になる。

## 情報源と保守

- CLI の仕様の正本は `agent-compat/logs/agent-logs/README.md` と `--help`。フラグ表を SKILL.md に複製しない。
- 各ツールのログ形式の正本は知識スキル（`skills/plugins/ai-tools-knowledge/skills/<tool>-logs/`、Claude Code は `skills/plugins/cc-knowledge/skills/claude-logs-investigate/`）。SKILL.md には CLI の利用者が知るべき欠損の要約だけを置く。
- アダプタを足す・欠損の扱いを変えたら、SKILL.md の「欠けている値の読み方」と `meta.requires_skills` を更新し、`meta.version` を上げる。
- インストールは扱わない（[tool-companion-skills](../../../../../maintenance/docs/tool-companion-skills.md)）。
