---
type: AI Tool
title: Antigravity と Claude Code の書き方の違い
description: Lists only the points where Google Antigravity (the IDE and the `agy` CLI) differs from Claude Code when writing skills, plugins, marketplaces, rules, memory files, hooks and subagents, with links to the minimal format samples in agent-compat/formats/antigravity and to the ai-tools-knowledge skills that are the source of truth, marking what the official docs leave undocumented. Use when porting or comparing a Claude Code skill, plugin, rule or subagent for Antigravity, or when checking which Claude Code mechanisms have no documented Antigravity equivalent.
tags: [antigravity, claude-code]
generated: { by: claude-opus-5-5, at: 2026-11-10T11:06:35Z }
status: draft
---

# Antigravity と Claude Code の書き方の違い

Claude Code を基準に、Google Antigravity（IDE と `agy` CLI）で書き方が変わる点だけを並べる。仕組みの詳細と出典は各知識スキル、実物の形は [formats/antigravity](../../formats/antigravity/README.md) を見る。

## スキル

- 置き場所: ワークスペースは `.agents/skills/<name>/`（旧 `.agent/skills` も可）。グローバルは `~/.gemini/config/skills/<name>/`。公式 IDE ページは `~/.gemini/antigravity/skills/` と書いており食い違う（拾われなければ両方を見る）。
- frontmatter は `name`（任意、既定はフォルダ名）と `description`（必須）の2つだけが文書化されている。
- 呼び出し: 名前と description だけを見て Agent が自動で読む。確実に使わせたいときはプロンプトで名前を出す。`/skill-name` で呼べるかは未確認。
- `allowed-tools`・`disable-model-invocation`・引数・`` !`command` `` の動的注入・`context: fork` は文書化されていない。頼らない。明示呼び出しの手順書に近いのは `/workflow-name` で呼ぶ Workflows（ファイルの置き場所は未確認）。
- 任意フォルダの名前例は `scripts/`・`examples/`・`resources/`。
- サンプル: [skill/antigravity-sample-skill/SKILL.md](../../formats/antigravity/skill/antigravity-sample-skill/SKILL.md)。出典: [antigravity-skills](../../../skills/plugins/ai-tools-knowledge/skills/antigravity-skills/SKILL.md)。

## プラグインとマーケットプレイス

- マニフェストはドットフォルダではなく、プラグインルート直下の `plugin.json`（必須の目印。`{ "name": "..." }`、name の既定はディレクトリ名）。
- 同梱できるのは `skills/`・`rules/`（`<rule-name>.md`）・`agents/`・`mcp_config.json`・`hooks.json`。
- 自動で見る場所はワークスペースの `.agents/plugins/`（または `_agents/plugins/`）と `~/.gemini/config/plugins/`。
- `agy plugin` で `install <target>`（`plugin@marketplace` 形式可）・`import`（gemini か claude から取り込み）・`validate`・`link <mp> <target>`（マーケットプレイスへのリンク生成）・`enable`／`disable` ができる。
- マーケットプレイス定義ファイルの書式は未確認。
- サンプル: [plugin/plugin.json](../../formats/antigravity/plugin/plugin.json)。出典: [antigravity-skills](../../../skills/plugins/ai-tools-knowledge/skills/antigravity-skills/SKILL.md)、[agy-cli-docs](../../../skills/plugins/ai-tools-knowledge/skills/agy-cli-docs/SKILL.md)（`output/help_result.yaml`）。

## ルール

- `.claude/rules/*.md`（`paths`）に当たるのは `.agents/rules/*.md`（旧 `.agent/rules/` も可）。
- frontmatter の `trigger` は `always_on`・`glob`・`model_decision`・`manual` の4種。キー名は公式ドキュメントに無く、IDE で作ったルールから確かめたもの。
- glob 対象のキー名は資料で食い違う。`tools/agents-rules` は IDE で作ったルールを見て `glob:` を出し、antigravity-memory は `globs:` と書いている（どちらが正しいか未確認）。glob は1行・カンマ区切り・250文字まで。
- 1ファイル12,000文字まで。本文から `@filename` で他ファイルを参照できる。
- サンプル: [rule/src.example.md](../../formats/antigravity/rule/src.example.md)（`tools/agents-rules` の出力と同じ形）。出典: [antigravity-memory](../../../skills/plugins/ai-tools-knowledge/skills/antigravity-memory/SKILL.md)。

## メモリファイル

- ワークスペース直下の `GEMINI.md` と `AGENTS.md` を読む。グローバルは `~/.gemini/GEMINI.md` だけ。
- `CLAUDE.md` を読むという記載は無い。
- サブディレクトリに置いた `GEMINI.md`／`AGENTS.md` を読むか、いつ読み直すかは未文書。両方あるときの優先順も未文書。
- 会話から自動でメモリを作る機能の記載は無い。
- 出典: [antigravity-memory](../../../skills/plugins/ai-tools-knowledge/skills/antigravity-memory/SKILL.md)。

## フック

- プラグインが `hooks.json` を同梱できることだけ確認できる。置き場所・イベント名・入出力の書式は未確認（公式 `docs/hooks`・`docs/ide/hooks` を antigravity-docs で取得して確かめる）。
- 出典: [antigravity-skills](../../../skills/plugins/ai-tools-knowledge/skills/antigravity-skills/SKILL.md)、[antigravity-docs](../../../skills/plugins/ai-tools-knowledge/skills/antigravity-docs/SKILL.md)。

## サブエージェント

- 置き場所は `.agents/agents/<name>.md` か `.agents/agents/<name>/agent.md`（グローバルは `~/.gemini/config/agents/`、プラグインは `agents/`）。`.claude/agents/` を読むかは未確認。
- frontmatter は `name`・`description`（どちらも必須）・`tools`・`mainAgent`・`subagent`・`model`（`inherit`／`flash`／`pro`）・`commandExecutionPolicy`（`off`／`auto`／`eager`／`sandbox`）・`mcpServers`・`skills`／`plugins`。
- `tools` に存在しないツール名を書くとハングすることがある。
- 起動は `invoke_subagent` ツール。作業場所を `inherit`／`branch`（git worktree）／`share` から選べる。組み込みは `research`・`browser`・`self`。ネストは10階層まで。
- サンプル: [agent/code-auditor.md](../../formats/antigravity/agent/code-auditor.md)。出典: [antigravity-subagents](../../../skills/plugins/ai-tools-knowledge/skills/antigravity-subagents/SKILL.md)。
