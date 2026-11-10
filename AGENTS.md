@./README.md

## このフォルダの責務

- 置くのは、マルチ AI 対応の仕組み（`agent-tooling/`）、ツール固有書式のサンプル（`formats/`）、Claude Code との相違点（`docs/differences/`）だけ。スキルの実体や、他ツール向けのスキルのコピーは置かない。
- 他ツールの使い方を説明する知識は `skills/plugins/ai-tools-knowledge/` のスキルに書く。「そのツールで読ませて初めて意味がある実物」だけを `formats/<tool>/` のサンプルにし、知識スキルからリンクする。迷ったら知識側に置く。
- `formats/` のサンプルに `AGENTS.md`・`CLAUDE.md`・`GEMINI.md` という名前を付けない（このリポジトリのフックや `agents-rules` が本物の指示として読む）。`AGENTS.example.md` のように名前を変える。サンプルの `SKILL.md` は `formats/<tool>/skill/<name>/` に置く。`formats/.format-samples` があるので、スキル走査はこの下を数えない。
- `docs/differences/` は OKF の概念ドキュメントで書く（`maintenance/docs/` と同じ frontmatter）。事実は知識スキルとその参照ファイルに基づかせ、確認できないことは「未確認」と書く。
