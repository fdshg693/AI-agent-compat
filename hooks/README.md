# hooks/

複数の AI コーディングツール（Claude Code・Codex・Cursor・Antigravity・Kilo Code）へ同じフックとコンテキスト注入を届ける仕組み。

- [agent-tooling/](agent-tooling/README.md) — フックの正本（scenario ごとの `hook.yaml` とアダプタ）、配布用の生成物とカタログ、CLI `agent-context-check`・`agent-sessions`。書き方は [agent-tooling/AGENTS.md](agent-tooling/AGENTS.md)

配布の流れと設計判断は [hook-distribution](../../maintenance/docs/hook-distribution.md)。
