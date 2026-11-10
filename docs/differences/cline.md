---
type: AI Tool
title: Cline と Claude Code の相違点
description: Lists only the points where Cline differs from Claude Code when writing skills, plugins, rules, memory files, hooks and subagents, based on the ai-tools-knowledge Cline skills and the docs.cline.bot snapshot they cite, with links to the minimal format samples under agent-compat/formats/cline. Use when porting a Claude Code skill or setting to Cline, writing a Cline-specific file, or checking which Claude Code mechanisms have no Cline equivalent.
tags: [cline, claude-code]
generated: { by: claude-opus-5-5, at: 2026-11-10T11:08:08Z }
status: draft
---

# Cline と Claude Code の相違点

Claude Code を基準に、Cline で書き方が変わる点だけを並べる。仕組みの説明は知識スキル、実物の書式は [formats/cline](../../formats/cline/README.md) にある。

## スキル

- 置き場所: プロジェクトは `.cline/skills/`（推奨）・`.clinerules/skills/`・`.claude/skills/`。グローバルは `~/.cline/skills/`。同名ならグローバル側が優先される（Claude Code の Personal > Project と同じ向き）。
- frontmatter: 公式に書かれているのは `name`（ディレクトリ名と完全一致）と `description`（最大 1024 文字）だけ。
- 起動: description が依頼に合うと `use_skill` ツールで読み込まれる。チャットで `/<skill名>` と打っても明示起動できる。スキルごとに UI のトグルで有効/無効を切り替える。
- Claude Code の `allowed-tools`・`disable-model-invocation`・`user-invocable`・`` !`command` `` に当たるものは公式ドキュメントに記載がない（未確認）。書いても効く保証はない。明示起動専用にしたいときはトグルで切るしかない。
- サンプル: [skill/cline-sample-skill](../../formats/cline/skill/cline-sample-skill/SKILL.md)。根拠: [cline-skill-writer](../../../skills/plugins/ai-tools-knowledge/skills/cline-skill-writer/SKILL.md)、公式 `customization/skills`。

## プラグイン

- Claude Code のプラグイン（`.claude-plugin/plugin.json` でスキル・フック等を束ねる）とは別物。Cline のプラグインは `AgentPlugin` を export する `.ts`/`.js` のコードで、ツール・フック・スラッシュコマンド・イベントを足す。
- 対象は SDK・CLI・Kanban だけで、VS Code / JetBrains 拡張では使えない。
- マニフェストは `package.json` の `cline.plugins`（`paths` と `capabilities`）。無ければ自動探索。`@cline/*` はホストが提供するので optional な `peerDependencies` に書く。
- 入れ方は `cline plugin install <file URL | git | npm: | ローカルパス>`。`--cwd <path>` で `<path>/.cline/plugins/` に入る。グローバルは `~/.cline/plugins/`。
- マーケットプレイス（Claude Code の `marketplace.json` に当たるもの）はナレッジスキルに記載がない（未確認）。
- プラグインに `skills/` を同梱する形式は公式ガイドにあるが、スキルとして一覧登録されるかは環境次第。確実に使わせるなら通常のスキル置き場に入れる。
- サンプル: [personal-info](../../formats/cline/personal-info/README.md)。根拠: [cline-plugin-writer](../../../skills/plugins/ai-tools-knowledge/skills/cline-plugin-writer/SKILL.md)、公式 `customization/plugins`。

## ルール

- 置き場所はプロジェクトの `.clinerules/`（`.md` と `.txt` を全部結合して読む）。グローバルは `Documents/Cline/Rules`（`~/.cline/rules/` も読む）。ワークスペース側が優先。
- 条件付きルールは frontmatter の `paths:`（glob の配列）。Claude Code の `.claude/rules/` の `paths:` と同じキー名。frontmatter なしは常時有効、`paths: []` は無効。
- 判定に使う「今のファイル」は、メッセージ中のパス・開いているタブ・表示中のファイル・編集したファイル・これから編集するファイル。
- `.cursorrules`・`.windsurfrules`・`AGENTS.md` もルールとして自動検出され、どれも UI で個別にトグルできる。
- このリポジトリは `tools/agents-rules` で AGENTS.md から `.clinerules/agents-*.md` を作る（frontmatter は `paths:` 1 個）。
- サンプル: [rule/src.example.md](../../formats/cline/rule/src.example.md)。根拠: [cline-rule-writer](../../../skills/plugins/ai-tools-knowledge/skills/cline-rule-writer/SKILL.md)、公式 `customization/cline-rules`。

## メモリファイル

- `CLAUDE.md` ではなく `AGENTS.md` を読む。公式に書かれているのはプロジェクトルートと `~/.agents/AGENTS.md` の 2 か所だけ。
- サブディレクトリの `AGENTS.md`（Claude Code のネスト `CLAUDE.md` に当たるもの）は公式に記載がない（未確認）。ディレクトリ別の指示は条件付きルールで書く。
- `@path` での取り込みや auto memory に当たる仕組みは記載がない（未確認）。セッションをまたぐ状態は Memory Bank（`memory-bank/` とそれを読ませるルール）という運用手法で持つ。
- 根拠: [cline-memory](../../../skills/plugins/ai-tools-knowledge/skills/cline-memory/SKILL.md)（`memory-reference.md`）。

## フック

- Claude Code のような settings 内の command hook（stdin に JSON を渡す形）は無い。フックはプラグインの `hooks`（`beforeTool`・`afterTool`・`beforeRun`・`afterRun`・`beforeModel`・`afterModel`・`onEvent`）でコードとして書く。
- 設定ディレクトリに `.cline/hooks/`・`~/.cline/hooks/` があり、CLI に `--hooks-dir` もあるが、そこに置くファイルの書式は未確認。
- このため agent-tooling のフック配布は Cline を対象外にしている（[hook-distribution](../../../maintenance/docs/hook-distribution.md)）。
- 根拠: [cline-plugin-writer](../../../skills/plugins/ai-tools-knowledge/skills/cline-plugin-writer/SKILL.md)（`plugin-reference.md` の Hook stages）。

## サブエージェント

- Claude Code のように定義ファイルで自作するサブエージェントは、ナレッジスキルに記載がない。設定ディレクトリに `.cline/agents/`（`agents.yaml`）があることだけ分かっていて、書式は未確認。
- 組み込みの `use_subagents` ツールが読み取り専用の調査エージェントを並列に走らせる（ファイル編集・MCP・ネストは不可。実験的機能）。
- 根拠: [cline-docs](../../../skills/plugins/ai-tools-knowledge/skills/cline-docs/SKILL.md)（公式 `features/subagents`、`getting-started/config`）。
