---
type: AI Tool
title: GitHub Copilot と Claude Code の違い
description: Lists only what differs when writing skills, plugins, marketplaces, custom instructions, AGENTS.md, hooks and custom agents for GitHub Copilot (Copilot CLI, VS Code agent mode, Copilot cloud agent) instead of Claude Code — skill folders under .github/skills, root plugin.json and .github/plugin/marketplace.json, enabledPlugins in .github/copilot/settings.json, copilot-instructions.md and applyTo-scoped .instructions.md files, root hooks.json in plugins, and *.agent.md agents — with links to the format samples in agent-compat/formats/copilot and the knowledge skills that are the source of truth. Use when porting a Claude Code skill, plugin, rule or subagent to GitHub Copilot, or when checking whether a Claude Code mechanism has a Copilot equivalent.
tags: [copilot, claude-code]
generated: { by: claude-opus-5-5, at: 2026-11-10T11:07:41Z }
status: draft
---

# GitHub Copilot と Claude Code の違い

Claude Code を基準に、GitHub Copilot（Copilot CLI・VS Code・Copilot cloud agent）で書き方が変わる点だけを並べる。ホストごとに対応が違うことがあるので、詳細は各節の知識スキルを読む。書式の実物は [formats/copilot](../../formats/copilot/README.md) にある。

## スキル

- **置き場所**: リポジトリの `.github/skills/<name>/SKILL.md`。`.claude/skills/` と `.agents/skills/` も読まれる。個人用（personal skill）の場所は知識スキルに記載がない（未確認）。
- **frontmatter**: `name`（小文字とハイフン、通常はディレクトリ名と同じ）と `description` が必須。任意で `license` と `allowed-tools`。仕様にない独自項目を足しても Copilot は解釈しない前提で書く。サンプル: [SKILL.md](../../formats/copilot/skill/copilot-sample-skill/SKILL.md)。
- **`allowed-tools`**: 項目名は Claude Code と同じだが、目的は「スクリプト実行を確認なしで許可する」こと。`shell`/`bash` を許可すると確認なしで端末コマンドが走る。使えるツール名は GitHub のドキュメントで確認する。
- **呼び出し**: `description` を見て Copilot が関連性を判断して読み込む。CLI では `/skills list` で読み込みを確認できる。明示起動の記法は知識スキルに記載がない（未確認）。
- **`disable-model-invocation`・`!command`**: 相当する仕組みは知識スキルに記載がない（未確認）。
- **配布**: `gh skill preview`・`install`・`update`・`publish` で単体スキルを配れる。

知識スキル: [copilot-writing-skills](../../../skills/plugins/ai-tools-knowledge/skills/copilot-writing-skills/SKILL.md)。基準: [writing-skill](../../../skills/plugins/cc-knowledge/skills/writing-skill/SKILL.md)。

## プラグインとマーケットプレイス

- **マニフェスト**: プラグインルートの `plugin.json`（Claude Code は `.claude-plugin/plugin.json`）。必須は `name` だけ。`agents`・`skills` の既定は `agents/`・`skills/`。`hooks`・`mcpServers`・`lspServers` はファイルパスかインラインで指定する。`.plugin/plugin.json`・`.github/plugin/plugin.json`・`.claude-plugin/plugin.json` も検出されるが、優先順はホストごとに確認が要る。サンプル: [plugin.json](../../formats/copilot/plugin/plugin.json)。
- **同梱できるもの**: agents・skills・commands・hooks・MCP に加えて LSP サーバー（`lsp.json`）。
- **マーケットプレイス**: `.github/plugin/marketplace.json`。トップレベルに `name`・`owner`・`plugins`。`.claude-plugin/marketplace.json` も検出される。サンプル: [marketplace.json](../../formats/copilot/plugin/marketplace.json)。
- **登録と有効化**: CLI は `copilot plugin marketplace add OWNER/REPO` → `copilot plugin install NAME@MARKETPLACE`。リポジトリ単位では `.github/copilot/settings.json` の `extraKnownMarketplaces` と `enabledPlugins` に書く（CLI と cloud agent の両方が読む）。VS Code は `~/.copilot/installed-plugins/` から CLI のプラグインを拾うことがある。
- **パスの記号**: Copilot 形式で `${CLAUDE_PLUGIN_ROOT}` を前提にしない。知識スキルの LSP 例は `${PLUGIN_ROOT}` を使うが、展開されるかはクライアント次第（未確認）。

知識スキル: [copilot-writing-plugins](../../../skills/plugins/ai-tools-knowledge/skills/copilot-writing-plugins/SKILL.md)。基準: [writing-plugins](../../../skills/plugins/cc-knowledge/skills/writing-plugins/SKILL.md)。

## ルール（instructions）

- Claude Code の `.claude/rules/*.md` に当たるのは `.github/instructions/<name>.instructions.md`。frontmatter の `applyTo` に glob（カンマ区切り可）を書く。サンプル: [typescript.instructions.example.md](../../formats/copilot/rule/typescript.instructions.example.md)。
- VS Code では `applyTo` が無いファイルは自動適用されず、手動で添付するものになる。GitHub.com では path-specific instructions を使えるのは cloud agent と code review。片方だけに効かせる `excludeAgent` がある。
- VS Code 専用の frontmatter と GitHub.com 専用の frontmatter は別物として扱う。

知識スキル: [writing-copilot-instructions](../../../skills/plugins/ai-tools-knowledge/skills/writing-copilot-instructions/SKILL.md)。基準: [writing-rules](../../../skills/plugins/cc-knowledge/skills/writing-rules/SKILL.md)。

## メモリファイル

- リポジトリ全体の常時ルールは `.github/copilot-instructions.md`（素の Markdown）。サンプル: [copilot-instructions.example.md](../../formats/copilot/memory/copilot-instructions.example.md)。
- `AGENTS.md` も読む。リポジトリ内の任意のディレクトリに置け、作業場所に最も近いものが優先される。CLI は `--no-custom-instructions` で `AGENTS.md` などの読み込みを止められる。
- `CLAUDE.md` を読むかどうかはホストごとに公式ドキュメントで確認する、とだけ書かれている（未確認）。
- 複数の instructions が同時に効くとき、適用順を前提にしない。

知識スキル: [writing-copilot-instructions](../../../skills/plugins/ai-tools-knowledge/skills/writing-copilot-instructions/SKILL.md)、[copilot-cli-docs](../../../skills/plugins/ai-tools-knowledge/skills/copilot-cli-docs/SKILL.md)。

## フック

- プラグインでは、Copilot 形式はルートの `hooks.json`、Claude 形式は `hooks/hooks.json`。
- イベントは `SessionStart`・`UserPromptSubmit`・`PreToolUse`・`PostToolUse`・`PreCompact`・`SubagentStart`・`SubagentStop`・`Stop` など。
- `hooks.json` の中身の書式・入出力は知識スキルに記載がない（未確認）。公式の CLI hooks reference と VS Code の Hooks Reference を見る。

知識スキル: [copilot-writing-plugins](../../../skills/plugins/ai-tools-knowledge/skills/copilot-writing-plugins/SKILL.md)（`references/components.md`）、[vscode-copilot-docs](../../../skills/plugins/ai-tools-knowledge/skills/vscode-copilot-docs/SKILL.md)。基準: [writing-hooks](../../../skills/plugins/cc-knowledge/skills/writing-hooks/SKILL.md)。

## サブエージェント（custom agents）

- Copilot では「custom agent」。プラグイン内では `agents/<name>.agent.md`（拡張子が `.agent.md`）。frontmatter に `name`・`description`・`tools`（例 `["view", "bash"]`）。ツール名は Claude Code と違い、クライアントごとに変わり得る。サンプル: [security-reviewer.agent.example.md](../../formats/copilot/agent/security-reviewer.agent.example.md)。
- CLI では `--agent <agent>` で指定し、`/agent` で確認する。
- プラグイン外（リポジトリ直下など）に置く場所は知識スキルに記載がない（未確認）。

知識スキル: [copilot-writing-plugins](../../../skills/plugins/ai-tools-knowledge/skills/copilot-writing-plugins/SKILL.md)（`references/components.md`）。基準: [writing-subagents](../../../skills/plugins/cc-knowledge/skills/writing-subagents/SKILL.md)。
