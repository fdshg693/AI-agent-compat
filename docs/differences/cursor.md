---
type: AI Tool
title: Cursor と Claude Code の書き方の違い
description: Lists only the points where Cursor (the AI code editor and its `agent` CLI) differs from Claude Code when writing skills, plugins, marketplaces, rules, memory files, hooks and subagents, with links to the minimal format samples in agent-compat/formats/cursor and to the ai-tools-knowledge skills that are the source of truth. Use when porting or comparing a Claude Code skill, plugin, rule, hook or subagent for Cursor, or when checking which Claude Code frontmatter fields Cursor does not support.
tags: [cursor, claude-code]
generated: { by: claude-opus-5-5, at: 2026-11-10T11:06:35Z }
status: draft
---

# Cursor と Claude Code の書き方の違い

Claude Code を基準に、Cursor で書き方が変わる点だけを並べる。仕組みの詳細と出典は各知識スキル、実物の形は [formats/cursor](../../formats/cursor/README.md) を見る。

## スキル

- 置き場所: `.cursor/skills/<name>/` か `.agents/skills/<name>/`（ユーザーは `~/.cursor/skills/`・`~/.agents/skills/`）。互換のため `.claude/skills/`・`.codex/skills/` も読む。
- モノレポでは配下の `.cursor/skills/` も拾い、そのディレクトリ配下に自動で絞られる。
- frontmatter: `name`（必須、フォルダ名と一致）・`description`（必須）・`paths`（glob、文字列かリスト）・`disable-model-invocation`・`metadata`。
- 呼び出し: description による自動適用と `/skill-name`。`disable-model-invocation: true` で `/skill-name` 専用になる（Claude Code と同名・同じ意味）。
- `allowed-tools`、`` !`command` `` の動的注入、`${CLAUDE_SKILL_DIR}` などの置換変数は無い。混ぜて書かない。
- サンプル: [skill/cursor-sample-skill/SKILL.md](../../formats/cursor/skill/cursor-sample-skill/SKILL.md)。出典: [cursor-skill-use](../../../skills/plugins/ai-tools-knowledge/skills/cursor-skill-use/SKILL.md)（`reference.md`）。

## プラグインとマーケットプレイス

- マニフェストは `.cursor-plugin/plugin.json`。必須は `name` だけ。
- 同梱できるのは rules（`.mdc`）・skills・agents・commands・MCP（`mcp.json`）・hooks。既定ディレクトリから自動で見つかり、マニフェストで別パスも指定できる（完全なスキーマは未確認）。
- ローカル試験は `~/.cursor/plugins/local/<name>/` に置いて再起動か **Developer: Reload Window**。
- 公開は cursor.com/marketplace/publish から審査に出す（オープンソース必須・全件手動レビュー）。複数プラグインのリポジトリは `.cursor-plugin/marketplace.json` を置く（中身の書式は未確認）。
- Teams／Enterprise にはチームマーケットプレイス（Dashboard → Plugins、GitHub から取り込み、Default Off／Default On／Required の配布モード）がある。
- サンプル: [plugin/.cursor-plugin/plugin.json](../../formats/cursor/plugin/.cursor-plugin/plugin.json)。出典: [cursor-plugin-use](../../../skills/plugins/ai-tools-knowledge/skills/cursor-plugin-use/SKILL.md)。

## ルール

- `.claude/rules/*.md`（`paths`）の代わりに `.cursor/rules/**/*.mdc`。拡張子は `.mdc` 必須で、`.md` は無視される。
- frontmatter は `alwaysApply`・`description`・`globs` の組み合わせで、常時／ファイル一致／Agent 判断／`@rule-name` 手動 の4通りになる。
- ルールは Agent（Chat）だけに効く。Tab と Inline Edit（Ctrl+K）には効かない。
- サンプル: [rule/rule.example.mdc](../../formats/cursor/rule/rule.example.mdc)（`tools/agents-rules` の出力と同じ形）。出典: [cursor-memory](../../../skills/plugins/ai-tools-knowledge/skills/cursor-memory/SKILL.md)（`memory.md`）。

## メモリファイル

- `AGENTS.md`（ルートと任意のサブディレクトリ、親と結合して深い方が優先）を読む。frontmatter なしの素の Markdown。
- `CLAUDE.md` も `AGENTS.md` と同じように読み、常に適用する（`alwaysApply` は無視）。`@./AGENTS.md` だけの `CLAUDE.md` だと両方読まれて重複しうる。
- 個人設定は User Rules（Customize → Rules、ファイルではない）、組織は Team Rules（ダッシュボード）。優先順は Team → Project → User。
- 旧 `.cursorrules` は非推奨予定。
- 出典: [cursor-memory](../../../skills/plugins/ai-tools-knowledge/skills/cursor-memory/SKILL.md)。

## フック

- `settings.json` ではなく専用の `hooks.json`（`"version": 1`）。プロジェクトは `.cursor/hooks.json`（コマンドはリポジトリルート相対）、ユーザーは `~/.cursor/hooks.json`（`~/.cursor/` 相対）。
- イベント名は小文字始まり（`beforeShellExecution`・`preToolUse`・`afterFileEdit`・`stop` など）。エディタ固有の `beforeTabFileRead`・`workspaceOpen` もある。
- stdin／stdout とも JSON。終了コード 2 で拒否、それ以外の失敗は処理続行（fail-open）。
- Cloud agent ではコマンド型だけが動き、ユーザーフックと一部イベント（`sessionStart` など）は動かない。
- プラグイン内での hooks の置き場所は未確認。
- サンプル: [hooks/hooks.json](../../formats/cursor/hooks/hooks.json)。出典: [cursor-sdk-use](../../../skills/plugins/ai-tools-knowledge/skills/cursor-sdk-use/SKILL.md)（`hooks.md`・`references/hooks.md`）。

## サブエージェント

- 置き場所は `.cursor/agents/*.md`（ユーザーは `~/.cursor/agents/`）。`.claude/agents/`・`.codex/agents/` も読み、`.cursor/` が優先。
- frontmatter は `name`・`description`・`model`（既定 `inherit`）・`readonly`・`is_background`。`tools` に当たるフィールドは知識スキルに無い（未確認）。
- 組み込みは `Explore`・`Bash`・`Browser`。サブエージェントから起動できるのは1階層まで。
- サンプル: [agent/security-auditor.md](../../formats/cursor/agent/security-auditor.md)。出典: [cursor-cli-use](../../../skills/plugins/ai-tools-knowledge/skills/cursor-cli-use/SKILL.md)（`memos/05-reusable-agents-pointer.md`）、[cursor-sdk-use](../../../skills/plugins/ai-tools-knowledge/skills/cursor-sdk-use/SKILL.md)（`subagents.md`）。
