@./README.md

## このフォルダの責務

- 置くのは、マルチ AI 対応の仕組み（`hooks/agent-tooling/`：フック・コンテキスト注入）、各ツールのローカルログを読むツール（`logs/agent-logs/`：検索・集計 CLI）、ツール固有書式のサンプル（`formats/`）、Claude Code との相違点（`docs/differences/`）、それらの CLI に付属する使い方スキルのプラグイン（`_plugin/agent-compat-tools/`）だけ。スキルの実体は `_plugin/` の使い方スキルを例外として置かない。他ツール向けのスキルのコピーも置かない。
- `_plugin/agent-compat-tools/` は `tools/_plugin/my-tools` と同じ形の Claude Code プラグイン。agent-compat に CLI を足したら、使い方スキルはここに足す（別プラグインを作らない）。スキルは使い方と判断だけを書き、ログ形式などの仕様は知識スキルに置く（[tool-companion-skills](../maintenance/docs/tool-companion-skills.md)）。`skills/CATALOG.md` は生成物。
- 他ツールの使い方を説明する知識は `skills/plugins/ai-tools-knowledge/` のスキルに書く。「そのツールで読ませて初めて意味がある実物」だけを `formats/<tool>/` のサンプルにし、知識スキルからリンクする。迷ったら知識側に置く。
- `formats/` のサンプルに `AGENTS.md`・`CLAUDE.md`・`GEMINI.md` という名前を付けない（このリポジトリのフックや `agents-rules` が本物の指示として読む）。`AGENTS.example.md` のように名前を変える。サンプルの `SKILL.md` は `formats/<tool>/skill/<name>/` に置く。`formats/.format-samples` があるので、スキル走査はこの下を数えない。
- `docs/differences/` は OKF の概念ドキュメントで書く（`maintenance/docs/` と同じ frontmatter）。事実は知識スキルとその参照ファイルに基づかせ、確認できないことは「未確認」と書く。

## このフォルダだけを開いたとき

アンブレラ（fdshg693/AI）の `agent-compat/` として clone されている前提。共通の手順（Junction・フックの作り方、`_umbrella/` の扱い、2 段階コミット）は [repo-layout](../maintenance/docs/repo-layout.md#サブモジュールを単体で開く)。

- フックを足す・変えるときの入口は [hook-distribution](../maintenance/docs/hook-distribution.md)。フックのカタログを再生成したら、アンブレラ側で `just hooks-update`（アンブレラ自身）と `just sub-agent-hooks-update`（各サブモジュール）を実行する。
- 知識スキル（`_umbrella/ai-tools-knowledge/`・`_umbrella/cc-knowledge/`）はアンブレラの `skills/` サブモジュールにある。そこを直したらコミットは `skills/` で行う。他ツール向けのコピー（`.cline/skills/` 等）はアンブレラのルートで `just agent-compat-sync`。
