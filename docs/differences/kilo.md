---
type: AI Tool
title: Kilo Code と Claude Code の相違点
description: Lists only the points where Kilo Code (kilo.ai CLI/TUI/VS Code extension) differs from Claude Code when writing skills, plugins, rules, memory files, hooks and agents/modes, based on the ai-tools-knowledge Kilo skills and the kilo.ai/docs snapshot they cite, with links to the minimal format samples under agent-compat/formats/kilo. Use when porting a Claude Code skill or setting to Kilo Code, writing a Kilo-specific file, or checking which Claude Code mechanisms behave differently in Kilo.
tags: [kilo, claude-code]
generated: { by: claude-opus-5-5, at: 2026-11-10T11:08:08Z }
status: draft
---

# Kilo Code と Claude Code の相違点

Claude Code を基準に、Kilo Code で書き方が変わる点だけを並べる。仕組みの説明は知識スキル、実物の書式は [formats/kilo](../../formats/kilo/README.md) にある。

## スキル

- 置き場所: プロジェクトは `.kilo/skills/`、グローバルは `~/.kilo/skills/`。互換で `.agents/skills/` と `.claude/skills/` も読む（VS Code 拡張では `.claude/skills/` は Claude Code Compatibility を有効にしたときだけ）。`kilo.jsonc` の `skills.paths`・`skills.urls`（`index.json` を置いたリモート）でも足せる。
- 同名ならプロジェクト側が優先される。Claude Code（Personal > Project）とは逆。
- frontmatter: Agent Skills 仕様どおり `name`（64 文字以内、小文字・数字・ハイフン）・`description`（1024 文字以内）が必須、`license`・`compatibility`・`metadata` が任意。`name` とディレクトリ名の一致は、公式ページ内で「必須」と「不要」の両方の記述があり未確定。
- 起動: エージェントが description を見て `skill` ツールで読み込む。名前を挙げて「〜スキルを使って」と頼めば明示起動できる。スラッシュコマンドでの起動は未確認。追加・変更は `/reload` か新しいセッションで反映。
- `` !`command` ``: 使える。ただし実行されるのはグローバル側などの信頼された場所のスキルだけで、プロジェクトの `.kilo/skills/` とリモートのスキルでは実行されない。実行前に全コマンドをまとめて承認を求める。`KILO_DISABLE_SKILL_SHELL` で全面停止。
- Claude Code の `allowed-tools`・`disable-model-invocation`・`user-invocable` に当たる frontmatter は記載がない（未確認）。ツール制限は agent の `permission` で行う。
- サンプル: [skill/kilo-sample-skill](../../formats/kilo/skill/kilo-sample-skill/SKILL.md)。根拠: [kilo-skill-guide](../../../skills/plugins/ai-tools-knowledge/skills/kilo-skill-guide/SKILL.md)、[kilo-code-docs](../../../skills/plugins/ai-tools-knowledge/skills/kilo-code-docs/SKILL.md)（公式 `customize/skills`）。

## プラグイン

- Claude Code のプラグイン（スキル・フック等の束）とは別物。Kilo のプラグインは `@kilocode/plugin` の `Plugin` 型の TS/JS モジュールで、`export default { id, server }` を返す。カスタムツール、ツール実行への介入、chat・認証・プロバイダのフック、TUI 拡張ができる。
- 単一ファイルは `.kilo/plugin/`（グローバルは `~/.config/kilo/plugin/`）に置くだけで自動検出され、マニフェストは要らない。npm 依存があるときだけ `package.json`（`exports` の `./server`・`./tui`、`engines.opencode`）を用意する。`kilo.json` の `plugin` 配列や `kilo plugin <package>` でも入れられる。
- マーケットプレイスはあるが、配るのは agent・スキル・MCP サーバーで、プラグインは対象外。入れるとプロジェクトの `.kilo/agents/`・`.kilo/skills/`・`.kilo/kilo.json` などにファイルが書かれる。マーケットプレイスの定義ファイルを自分で書く仕組み（Claude Code の `marketplace.json` に当たるもの）は記載がない（未確認）。
- 実例: このリポジトリの `.kilo/plugin/agent_sessions.ts`（agent-tooling が出力するフック）。
- サンプル: [plugin/env-guard.ts](../../formats/kilo/plugin/env-guard.ts)。根拠: [kilo-plugin-writer](../../../skills/plugins/ai-tools-knowledge/skills/kilo-plugin-writer/SKILL.md)（`plugin-reference.md`）。

## ルール

- frontmatter で対象パスを絞る仕組み（Claude Code の `.claude/rules/` の `paths:`）は記載がない。ルールは frontmatter なしの Markdown で、どれを読むかは `kilo.jsonc` の `instructions`（ファイルパス・glob・URL の配列）で決める。glob はルールファイル自体を選ぶもので、編集対象のファイルで切り替わるものではない。
- 置き場所は `.kilo/rules/`。旧 `.kilocode/rules/` も互換で読む。グローバルは `~/.config/kilo/kilo.jsonc` の `instructions`。グローバル→プロジェクトの順に読み、ぶつかればプロジェクト側が優先。
- URL のルールはセッション開始時に取得し、届かなければ黙って飛ばす。
- サンプル: [rule/formatting.example.md](../../formats/kilo/rule/formatting.example.md)、[rule/kilo.example.jsonc](../../formats/kilo/rule/kilo.example.jsonc)。根拠: [kilo-memory-guide](../../../skills/plugins/ai-tools-knowledge/skills/kilo-memory-guide/SKILL.md)（`instructions.md`）。

## メモリファイル

- 主に `AGENTS.md` を読む（`AGENT.md` は代替）。互換で `CLAUDE.md` も読み、`CONTEXT.md` も認識する。グローバルは `~/.config/kilo/AGENTS.md`（互換で `~/.claude/CLAUDE.md`）。
- サブディレクトリの `AGENTS.md` は、そのディレクトリのファイルを Read したときに読み込まれ、`<system-reminder>` として差し込まれる（Claude Code のネスト `CLAUDE.md` に近い動き）。
- `AGENTS.md`・`AGENT.md` は書き込み保護されていて、AI が書き換えるにはユーザーの承認が要る。
- `@path` での取り込みや auto memory に当たる仕組みは記載がない（未確認）。Memory Bank 機能は廃止され、AGENTS.md への移行が推奨されている。
- 根拠: [kilo-memory-guide](../../../skills/plugins/ai-tools-knowledge/skills/kilo-memory-guide/SKILL.md)（`agents-md.md`）、公式 `customize/custom-instructions`。

## フック

- Claude Code のような settings 内の command hook は記載がない（未確認）。フックはプラグインの関数で書く（`tool.execute.before`・`tool.execute.after`・`chat.message`・`chat.params`・`permission.ask`・`event` など）。
- `tool.execute.before` で throw するとツールは失敗扱いになる。これでツール実行を止められる。
- 根拠: [kilo-plugin-writer](../../../skills/plugins/ai-tools-knowledge/skills/kilo-plugin-writer/SKILL.md)（`plugin-reference.md` の Hooks リファレンス）。

## サブエージェント・モード

- 旧 Mode は Agent にまとめられ、カスタムモードもサブエージェントも同じ agent 定義で書く。frontmatter の `mode` が `primary`（ユーザーが選ぶ）・`subagent`（`task` ツールか `@名前` で呼ばれる）・`all`（既定）を分ける。
- 置き場所は `.kilo/agents/`（`.kilo/agent/`、旧 `.kilocode/agents/` も可）。ファイル名から `.md` を除いたものが agent 名で、Claude Code のような `name` フィールドは無い。グローバルは `~/.config/kilo/agent/` と `~/.config/kilo/agents/` の両方が公式ページに出てくる（どちらが正しいか未確認）。`kilo.jsonc` の `agent` キーでも書ける。
- ツール制限は Claude Code の `tools` ではなく `permission`（`allow`／`ask`／`deny`、glob 可、最後に一致したものが勝つ）。他に `model`（`provider/model`）・`steps`・`temperature`・`top_p`・`hidden`・`color`・`disable`。
- 組み込みの agent（`code`・`plan`・`debug`・`ask`・`orchestrator`・`explore`・`general`）は同名で定義すると項目ごとに上書きされる。
- サンプル: [agent/code-reviewer.example.md](../../formats/kilo/agent/code-reviewer.example.md)。根拠: [kilo-agent-writer](../../../skills/plugins/ai-tools-knowledge/skills/kilo-agent-writer/SKILL.md)（`modes.md`・`subagents.md`）。

## スラッシュコマンド

- Claude Code の `.claude/commands/` に当たるのは Workflows（`.kilo/commands/<name>.md`、グローバルは `~/.config/kilo/commands/`）。`/<ファイル名>` で呼ぶ。frontmatter は `description`・`agent`・`model`・`variant`・`subtask`。
- 根拠: [kilo-code-docs](../../../skills/plugins/ai-tools-knowledge/skills/kilo-code-docs/SKILL.md)（公式 `customize/workflows`）。
