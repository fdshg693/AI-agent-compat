# 各エージェントツールの Hooks スキル

このディレクトリの実装（ネスト `AGENTS.md` 注入）ではなく、**各 AI エージェントツール自体の Hooks 仕様**を調べる／書くときに読むスキル。

`ai-tools.yaml` の 7 ツールのうち、**Hooks 専用の作成スキルがあるのは Claude Code と Codex だけ**。Cursor / Antigravity / GitHub Copilot には専用スキルが無く、公式ドキュメント参照スキルかプラグイン作成スキル経由で調べる。Kilo / Cline には command 型 `hooks.json` のスキルは無く、プラグインの TypeScript hook を扱うスキルがある。

| エージェント   | 専用の Hooks 作成スキル                                                             | 調べるときに読むスキル                                                                         |
| -------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Codex          | [codex-hooks](../../../codex-plugins/meta/skills/codex-hooks/SKILL.md)              | 同左                                                                                           |
| Claude Code    | [writing-hooks](../../../skills/plugins/cc-knowledge/skills/writing-hooks/SKILL.md) | 同左                                                                                           |
| Cursor         | なし                                                                                | [cursor-docs](../../../cursor-plugins/meta/skills/cursor-docs/SKILL.md)                        |
| Antigravity    | なし                                                                                | [antigravity-docs](../../../_agents/plugins/antigravity-meta/skills/antigravity-docs/SKILL.md) |
| Kilo           | なし（プラグイン hook はある）                                                      | [kilo-plugin-writer](../../../.kilo/skills/kilo-plugin-writer/SKILL.md)                        |
| Cline          | なし（プラグイン / CLI hook はある）                                                | [cline-plugin-writer](../../../.cline/skills/cline-plugin-writer/SKILL.md)                     |
| GitHub Copilot | なし                                                                                | [writing-plugins](../../../copilot-plugins/meta/writing-plugins/SKILL.md)                      |

このディレクトリの `generated/` にアダプタが無いのは Cline（command hook 契約が無い）と GitHub Copilot。

## Codex

- [codex-hooks](../../../codex-plugins/meta/skills/codex-hooks/SKILL.md) — `hooks.json` または `config.toml` の `[hooks]`。イベント選定、matcher、入出力契約、`/hooks` の信頼レビュー。同梱 [references/hooks.md](../../../codex-plugins/meta/skills/codex-hooks/references/hooks.md) が詳細スキーマ。
- 置き場所・スコープは [codex-settings](../../../codex-plugins/meta/skills/codex-settings/SKILL.md)。公式の一次情報は [codex-docs](../../../codex-plugins/meta/skills/codex-docs/SKILL.md)。

## Claude Code

- [writing-hooks](../../../skills/plugins/cc-knowledge/skills/writing-hooks/SKILL.md) — `.claude/settings.json` の hooks、`PreToolUse` / `PostToolUse` / `Stop` / `UserPromptSubmit` などの作成・レビュー。同梱 [hooks.md](../../../skills/plugins/cc-knowledge/skills/writing-hooks/hooks.md) がイベント・JSON スキーマの正本。
- 仕様が変わっていそうなら [claude-code-docs](../../../skills/plugins/cc-knowledge/skills/claude-code-docs/SKILL.md)（`code.claude.com`）。

## Cursor

専用の Hooks 作成スキルは無い。`.cursor/hooks.json` の仕様は公式ドキュメント参照スキルで調べる。

- [cursor-docs](../../../cursor-plugins/meta/skills/cursor-docs/SKILL.md) — `cursor.com/docs/hooks.md`。
- プラグインに hooks を同梱するなら [cursor-plugin-use](../../../cursor-plugins/meta/skills/cursor-plugin-use/SKILL.md)。
- Python SDK から `.cursor/hooks.json` を効かせるなら [cursor-sdk-use](../../../cursor-plugins/meta/skills/cursor-sdk-use/SKILL.md)（同梱 [hooks.md](../../../cursor-plugins/meta/skills/cursor-sdk-use/hooks.md)）。

## Antigravity

専用の Hooks 作成スキルは無い。`.agents/hooks.json` の仕様は公式ドキュメント参照スキルだけ。

- [antigravity-docs](../../../_agents/plugins/antigravity-meta/skills/antigravity-docs/SKILL.md) — `antigravity.google/docs/hooks` と `antigravity.google/docs/ide/hooks`。

## Kilo

`hooks.json` 型の command hook スキルは無い。Kilo の hook は `@kilocode/plugin` の TypeScript モジュール（`tool.execute.after` など）。

- [kilo-plugin-writer](../../../.kilo/skills/kilo-plugin-writer/SKILL.md) — プラグイン hook の設計。詳細は同梱 [plugin-reference.md](../../../.kilo/skills/kilo-plugin-writer/plugin-reference.md)。
- 公式仕様の確認は [kilo-code-docs](../../../.kilo/skills/kilo-code-docs/SKILL.md)（`automate/extending/plugins`）。

## Cline

stdin JSON の command hook 契約は無い（このディレクトリの `generated/` にも出さない）。プロジェクト `.cline/hooks/` は TS/JS。プラグインの lifecycle hook と CLI の `--hooks-dir` はある。

- [cline-plugin-writer](../../../.cline/skills/cline-plugin-writer/SKILL.md) — `hooks.beforeTool` などの lifecycle hook。詳細は同梱 [plugin-reference.md](../../../.cline/skills/cline-plugin-writer/plugin-reference.md)。
- CLI の `--hooks-dir` などは [cline-cli-docs](../../../.cline/skills/cline-cli-docs/SKILL.md)。
- 公式の一次情報は [cline-docs](../../../.cline/skills/cline-docs/SKILL.md)。

## GitHub Copilot

このディレクトリにアダプタは無い。専用の Hooks 作成スキルも無い。プラグイン同梱・SDK・CLI 監査で扱いが分かれる。

- [writing-plugins](../../../copilot-plugins/meta/writing-plugins/SKILL.md) — agent plugin に同梱する hooks。コンポーネント設計は同梱 [references/components.md](../../../copilot-plugins/meta/writing-plugins/references/components.md)。
- SDK のセッションライフサイクル hook は [github-copilot-sdk-docs](../../../copilot-plugins/meta/github-copilot-sdk-docs/SKILL.md)。
- Copilot CLI のプロンプト／ツール監査 hook は [github-copilot-observability-docs](../../../copilot-plugins/meta/github-copilot-observability-docs/SKILL.md)。
