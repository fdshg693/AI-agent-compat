# logs/

AI コーディングツールがこの PC に残すローカルログを読むツールを置く。フック（[../hooks/](../hooks/README.md)）とは独立したパッケージにする。

- [agent-logs/](agent-logs/README.md) — Claude Code・Cursor・Cline・Kilo Code・Antigravity・Codex のログを横断して一覧・検索・集計する CLI `agent-logs`（読み取り専用）

各ツールのログの所在・形式の正本は知識スキル（`skills/plugins/ai-tools-knowledge/skills/<tool>-logs/`、Claude Code は `skills/plugins/cc-knowledge/skills/claude-logs-investigate/`）にある。
