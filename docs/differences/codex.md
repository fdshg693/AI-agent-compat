---
type: AI Tool
title: Codex と Claude Code の違い
description: Lists only what differs when writing skills, plugins, marketplaces, command rules, AGENTS.md instructions and hooks for OpenAI Codex instead of Claude Code — skill locations under .agents/skills, the name/description-only SKILL.md frontmatter plus optional agents/openai.yaml, the .codex-plugin manifest and .agents/plugins marketplace, execpolicy .rules files, AGENTS.md discovery that runs once per session along the root-to-cwd path, and hook trust review — with links to the format samples in agent-compat/formats/codex and the knowledge skills that are the source of truth. Use when porting a Claude Code skill, plugin or hook to Codex, or when checking whether a Claude Code mechanism has a Codex equivalent.
tags: [codex, claude-code]
generated: { by: claude-opus-5-5, at: 2026-11-10T11:07:41Z }
status: draft
---

# Codex と Claude Code の違い

Claude Code を基準に、Codex で書き方が変わる点だけを並べる。仕組みの詳細は各節の知識スキルを読む。書式の実物は [formats/codex](../../formats/codex/README.md) にある。

## スキル

- **置き場所**: `.agents/skills/<name>/SKILL.md`。Codex は起動したディレクトリからリポジトリルートまでの各 `.agents/skills` を読む。ユーザー全体は `~/.agents/skills/`、ほかに `/etc/codex/skills`（ADMIN）と同梱スキル（SYSTEM）がある。Claude Code の `.claude/skills/` は読まない（読むという記載は知識スキルにない）。
- **frontmatter**: 必須は `name` と `description` だけ。Claude Code の `allowed-tools`・`disable-model-invocation` などに当たる項目は frontmatter には無い。
- **起動の制御**: 暗黙起動を止めるには、スキル内の `agents/openai.yaml` に `policy.allow_implicit_invocation: false` を書く（明示起動は残る）。同じファイルに UI 表示名・既定プロンプト・MCP ツール依存も書ける。サンプル: [SKILL.md](../../formats/codex/skill/codex-sample-skill/SKILL.md)、[agents/openai.yaml](../../formats/codex/skill/codex-sample-skill/agents/openai.yaml)。
- **呼び出し**: 明示起動は `$skill-name` のメンション、または `/skills`。Claude Code の `/skill-name` とは記号が違う。
- **無効化**: `~/.codex/config.toml` の `[[skills.config]]` に `path` と `enabled = false` を書く。
- **`!command`（動的コンテキスト注入）**: 相当する仕組みは知識スキルに記載がない（未確認）。
- **ツール許可**: スキル単位でツールを許可する仕組みは記載がない（未確認）。コマンドの実行可否は下記の rules で全体に設定する。

知識スキル: [codex-skill-authoring](../../../skills/plugins/ai-tools-knowledge/skills/codex-skill-authoring/SKILL.md)。基準: [writing-skill](../../../skills/plugins/cc-knowledge/skills/writing-skill/SKILL.md)。

## プラグインとマーケットプレイス

- **マニフェスト**: プラグインルートの `.codex-plugin/plugin.json`。`.codex-plugin/` には `plugin.json` だけを置き、`skills/` などはルート直下に置く。パスは `./` で始める。`interface`（`displayName`・`category` など）で表示を指定する。サンプル: [plugin.json](../../formats/codex/plugin/.codex-plugin/plugin.json)。
- **マーケットプレイス**: `.agents/plugins/marketplace.json`（リポジトリ）または `~/.agents/plugins/marketplace.json`（個人）。各項目は `source: { source: "local", path: "./..." }` と `policy`（`installation`・`authentication`）を持つ。`.claude-plugin/marketplace.json` も「legacy-compatible」として読まれる（ChatGPT デスクトップアプリの説明での記載）。サンプル: [marketplace.json](../../formats/codex/plugin/marketplace.json)。
- **登録**: `codex plugin marketplace add owner/repo` など。インストール先は `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`。
- **プラグイン同梱 hooks**: 既定は `hooks/hooks.json`（Claude Code と同じ位置）。フックには `PLUGIN_ROOT`・`PLUGIN_DATA` に加えて互換のため `CLAUDE_PLUGIN_ROOT`・`CLAUDE_PLUGIN_DATA` も渡る。

知識スキル: [codex-skill-authoring](../../../skills/plugins/ai-tools-knowledge/skills/codex-skill-authoring/SKILL.md)、[codex-docs](../../../skills/plugins/ai-tools-knowledge/skills/codex-docs/SKILL.md)（`build-plugins` ページ）。基準: [writing-plugins](../../../skills/plugins/cc-knowledge/skills/writing-plugins/SKILL.md)。

## ルール

- Codex の「rules」は指示ではなく、サンドボックス外で実行してよいコマンドを決める execpolicy。`~/.codex/rules/*.rules` または `.codex/rules/*.rules` に Starlark の `prefix_rule(pattern=..., decision="allow"|"prompt"|"forbidden")` を書く。複数一致では最も厳しい決定が勝つ。Claude Code の permissions 設定に近い役割。サンプル: [default.rules](../../formats/codex/rule/default.rules)。
- Claude Code の `.claude/rules/*.md`（glob で条件付きに注入する指示）に当たる仕組みは Codex に無い。

知識スキル: [codex-settings](../../../skills/plugins/ai-tools-knowledge/skills/codex-settings/SKILL.md)、[codex-memory](../../../skills/plugins/ai-tools-knowledge/skills/codex-memory/SKILL.md)。

## メモリファイル（AGENTS.md）

- `CLAUDE.md` ではなく `AGENTS.md` を読む。同じディレクトリに `AGENTS.override.md` があればそちらを優先し、`project_doc_fallback_filenames` で別名も足せる。1 ディレクトリにつき 1 ファイルだけ。
- 読むのはセッション開始時の 1 回だけ。範囲は `~/.codex/`（グローバル）と、プロジェクトルートから起動ディレクトリまでの経路上。作業中に触ったサブディレクトリの `AGENTS.md` は自動では読まれない。
- 合計サイズは `project_doc_max_bytes`（既定 32 KiB）で打ち切られる。
- `@./path` の取り込み記法についての記載は知識スキルにない（未確認）。
- 別機能として、過去のチャットから自動生成する memories（`features.memories`、既定オフ、`~/.codex/memories/`）がある。

知識スキル: [codex-memory](../../../skills/plugins/ai-tools-knowledge/skills/codex-memory/SKILL.md)。

## フック

- 置き場所は `~/.codex/hooks.json`・`.codex/hooks.json`、または `config.toml` のインライン `[hooks]`。`features.hooks = true` が前提。
- 構造（イベント → matcher グループ → ハンドラー）は似ているが、イベント名・出力フィールド・matcher が効くイベントが違う。ハンドラーの `type` で実行されるのは `command` と `mcp_tool` だけ（`prompt`/`agent` は読み込まれるが実行されない）。
- 追加・変更したフックは `/hooks` で信頼するまで実行されない。プロジェクトの `.codex/` は信頼済みプロジェクトでしか読まれない。
- Windows 用の上書きに `commandWindows`（TOML では `command_windows`）がある。

知識スキル: [codex-hooks](../../../skills/plugins/ai-tools-knowledge/skills/codex-hooks/SKILL.md)。基準: [writing-hooks](../../../skills/plugins/cc-knowledge/skills/writing-hooks/SKILL.md)。

## サブエージェント

- フックに `SubagentStart`・`SubagentStop` イベントがあり、公式ドキュメントにもサブエージェントのページがある。ただしサブエージェント定義ファイルの書式・置き場所は知識スキルに記載がない（未確認）。必要なら [codex-docs](../../../skills/plugins/ai-tools-knowledge/skills/codex-docs/SKILL.md) で確認する。
