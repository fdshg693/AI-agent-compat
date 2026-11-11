## `hooks/` — 複数シナリオの注入フック

ネイティブ discovery が拾わないネスト `AGENTS.md` と、Claude Ruleを触ったパスへ注入するフック、およびAIエージェントのセッションを登録・一覧するフックを、独立した scenario として実装・配布するソースとビルド成果。

各エージェントツール自体の Hooks 仕様を調べるときは [REFERENCES.md](REFERENCES.md)。

### 編集してよい場所

- `core/` — ツール非依存のパス正規化・コマンド解析・glob照合
- `scenarios/` — `nested_agents_md` / `scoped_rules` / `agent_sessions` の入力・探索契約と、配布・登録のメタデータ `hook.yaml`（Claude 専用フックは `hook.yaml` と seed だけ）
- `../adapters/` — エージェント差分（イベント、注入チャネル、サイズ上限）
- `build/` — 相対 import を 1 ファイルへインライン化するビルダー

`generated/` は生成物。手編集しない。ソースまたは `.claude/rules/` を変えたら `just --justfile agent-compat/agent-tooling/justfile generate`（lefthook も同じ入力変更で再生成する）。`nested_agents_md` は `AGENTS.md` だけを読み、`scoped_rules` は `.claude/rules/**/*.md` だけを読む。入力を相互に fallback させない。`agent_sessions` はファイルを読まず、開始/終了/CWD変更を `core/sessions.py` のレジストリ（env `AGENT_SESSIONS_DIR`、既定はユーザー単位）へ適用するだけで、コンテキストを注入しない。

### エージェントを足す

1. `scenarios/<scenario>/` に入力契約を置き、`../adapters/<agent>/<scenario>.py`（KiloはTS sidecarも）を追加する（`build/` / `tests/` / `generated/` は import しない）
2. `build/build.py` の `ENTRIES` に agent x scenario の `source` と `output` を足す。sidecarは `copies` で `../adapters/` から `generated/` へコピーする
3. `scenarios/<scenario>/hook.yaml` の `agents` に同じ agent を足す（`ENTRIES` と agent 集合が一致しないとビルドエラー）
4. ビルドして `generated/<agent>/<scenario>.*` と `generated/catalog.json` を更新する

### Claude 専用フック

旧 `.claude/hooks/*.py` の12本（`block_large_read` / `inject_env_vars` / `long_run_collector` / `long_run_statement_collector` / `stop_alert` / `task_tracker_session` / `summarize_read` / `summarize_webfetch` / `translate_prompt` / `recommend_skills` / `skill_usage_tracker` / `skill_enquete_stop`）も scenario として扱う。

- `scenarios/<id>/` には `hook.yaml`（`agents` は `claude` のみ）と seed テンプレートだけを置く。本体は `../adapters/claude/<id>.py`、共通処理は `../adapters/claude/common/`（旧 `_lib/`）。`ENTRIES` は `build.py` 末尾の Claude 専用フック一覧に id を足す
- `common/` は関数 import（`from .common.runtime import init_hook_context`）で使う。`runtime.foo()` のようなモジュール名前空間アクセスはインライン化後に残らない
- パスは `common/paths.py` に従う。フック自身の `config/<id>.yaml`・`.env`・`state/`・`logs/`・`alert.wav` は `hook_dir()`（配置されたファイルの隣。`.claude/hooks/` に置けば従来と同じ場所）、プロジェクト側（`.claude/tasks/`、スキルの roots）は `resolve_project_dir(payload)`（`CLAUDE_PROJECT_DIR` → stdin `cwd` → git top level → cwd）
- 子プロセスで自分を再実行するもの（`stop_alert` のポップアップ）は `__file__` ではなく `sys.argv[0]` とエントリ側の argv 分岐（`--popup`）を使う。インライン先の `if __name__ == "__main__":` は消えるため
- リポジトリ構造前提のもの（`recommend_skills` / `skill_usage_tracker` / `skill_enquete_stop`）は `distributable: false`。非stdlib依存は PEP 723（`skill_usage_tracker`）か `runner: uv-project` + `project_imports`（`recommend_skills`）で宣言する
- テストは `../../tests/claude_hooks/`。振る舞いは生成物を一時 `<project>/.claude/hooks/` にコピーして stdin JSON で流す
- `stop_alert` だけは Kilo 版もある（`hook.yaml` の `agents` が `claude` + `kilo`）。`../adapters/kilo/stop_alert.ts` が `session.idle`（`parentID` を持つサブエージェントのセッションは除く）で隣の `stop_alert.py` を待たずに spawn し、Python 側は `../adapters/claude/common/` の音・ポップアップ処理を `agent_tooling.adapters.claude.common.*` の絶対 import で再利用する。`alert.wav`・`.env`・`logs/` は `.kilo/plugin/` に置く

### `hook.yaml`

scenario ごとの配布・登録メタデータ。ビルドが検証し、`ENTRIES` のファイル一覧と合わせて `generated/catalog.json` に集約する（形式は [generated/README.md](generated/README.md)）。リポジトリ直下の `repo-hooks.yaml` がカタログの所在を指し、`skill-tools` はそこから読む。

```yaml
id: nested_agents_md # = ディレクトリ名
description: 1行の説明
distributable: true # 既定 true。false はこのリポジトリへの自己インストール専用
requires_tools: [aim] # 任意。repo-tools.yaml のキー（存在しなければビルドエラー）
agents:
  claude:
    runner: python # python（既定）/ uv-script（PEP 723 必須）/ uv-project（distributable: false 必須）
    project_imports: [aim_cli] # runner: uv-project のときだけ。残してよい非stdlib import
    registrations: # kilo 以外は1件以上。kilo は書かない（配置だけで有効）
      - event: PreToolUse
        matcher: Read|Edit|Write|Bash # 任意（CwdChanged のように非対応なら省略）
        timeout: 10 # ツール別に許可されたキーのみ
    seed_files: # 任意。初回だけ置く設定テンプレート
      - source: config.example.yaml # scenario ディレクトリ相対
        path: config/nested_agents_md.yaml # インストール先ディレクトリ相対
  kilo: {}
```

- 配布ファイル（`files` / `main`）は書かない。`ENTRIES` の `output` と `copies` から決まる（Kilo の `main` は TS）。
- `registrations` に `command` / `args` / `type` / `commandWindows` / `hooks` は書けない。コマンド文字列は配置先に依存するので installer が組み立てる。
- 許可キー: claude `event matcher timeout statusMessage async`、codex `event matcher timeout statusMessage additionalContextLimit`、cursor・antigravity `event matcher timeout`。増やすときは `build.py` の `REGISTRATION_KEYS` を更新する。

### 検証コマンド

```text
just --justfile agent-compat/agent-tooling/justfile test
just --justfile agent-compat/agent-tooling/justfile rules-check
just --justfile agent-compat/agent-tooling/justfile generate-check
```

Cline は stdin JSON の command hook が無いので生成対象に出さない。Kilo だけプラグイン形（薄い TS が隣の Python を spawn）。scenario ごとに TS + Python の 2 ファイル。

### ビルド契約

成果物の先頭は `#!/usr/bin/env python3`、次に（あれば）エントリモジュールの PEP 723 `# /// script` ブロック、その次がエントリモジュールの docstring。`from .` / `from agent_tooling.` / `from hooks.` は generated に残ってはいけない。stdlib 以外の import は、PEP 723 の `dependencies`（`runner: uv-script`。配布名と import 名がずれるものは `build.py` の `IMPORT_NAMES`）か `project_imports`（`runner: uv-project`）で宣言したものだけ残せる。manifest（`ENTRIES` の出力・sidecar・seed・`catalog.json`）にない generated artifact は generate で削除され、generate-check ではエラーになる。

インライン化はモジュールを1つの名前空間に平坦化するため、ビルダーは次をエラーにする。

- 異なるモジュール間のトップレベル名（関数・クラス・モジュール定数）の衝突。どちらかを改名するか、片方を re-export（`from x import NAME as NAME`）にする
- 残る import の束縛の食い違い（例: 片方が `import datetime`、もう片方が `from datetime import datetime`）。同じ書き方に揃える
- 関数内・ブロック内の相対 import / `agent_tooling` import（インライン化されずに残るため。モジュール最上位へ移す）と、未宣言の非stdlib import
- エントリ以外のモジュールの PEP 723 ブロック

インライン先モジュールの `if __name__ == "__main__":` 節は取り除かれる（エントリのものは残る）。

### 配置は skill-tools

lefthook もこのディレクトリの作業も、各ツールの hooks.json / 慣例ディレクトリへはコピーしない。配置と登録は `skill-tools hooks install`（[tools/skill-tools/README.md](../../../../tools/skill-tools/README.md)）が `generated/catalog.json` を読んで行う。登録するイベント・matcher・オプションの正本は各 `scenarios/<id>/hook.yaml` で、コマンド文字列（配置先パス・runner）は installer が組み立てる。生成元の `../adapters/` ではなく `generated/` を配置・実行する。

- 他プロジェクト: `skill-tools hooks install --agent <agent> <hook-id>`（配置先・登録ファイルの既定表は skill-tools の README）
- このリポジトリ: リポジトリ直下で `just hooks-install`（初回）/ `just hooks-update`（変更後）。設定は `.claude/skill-tools.hooks.yaml`、成果物は gitignore
- 全体の流れと設計判断: [maintenance/docs/hook-distribution.md](../../../../maintenance/docs/hook-distribution.md)

各ツール固有の注意（登録内容そのものは `hook.yaml` を見る）:

- Codex: `nested_agents_md` と `scoped_rules` は `.codex/hooks.json` の同じ matcher に2 commandとして並ぶ。`additionalContextLimit` は hooks.json 側のキー
- Claude Code: `permissionDecision` は返さない。`CwdChanged` は matcher 非対応なので `hook.yaml` に書かない
- Cursor: `postToolUse` の matcher は `Shell|Read|Write|Grep|Delete`（Shell だけに落とさない）。command はプロジェクトルート相対
- Antigravity: 同じスクリプトを `PreToolUse`（パス記録、必ず `decision: allow`）と `PreInvocation`（`injectSteps[].ephemeralMessage`）の両方に登録する
- Kilo: TS は `@kilocode/*` 以外の npm 依存を持たない単一ファイル。`tool.execute.after` で Python を spawn し、戻り `additionalContext` を `output.output` 末尾へ載せる。`args` は書き換えない。throw しない

#### agent_sessions（開始/終了/CWD変更の登録）

`agent_sessions` は注入せず、開始でエントリ作成・終了で削除・CWD変更で更新を、env `AGENT_SESSIONS_DIR`（既定はユーザー単位。Windows=`%TEMP%\agent-sessions`、POSIX=`$XDG_RUNTIME_DIR`→`$XDG_CACHE_HOME`→`~/.cache`）配下のレジストリへ適用するだけ。1 artifact がペイロードで分岐する。

- Claude: `SessionStart` / `CwdChanged` / `SessionEnd`（**無出力**）
- Codex: `SessionStart` / `SessionEnd`（**無出力**。CWD変更イベントは無く開始時CWDを保持）
- Cursor: `sessionStart` / `sessionEnd`（CWDは `workspace_roots[0]`。クラウドでは発火しない）
- Antigravity: 初回 `PreInvocation`（`invocationNum==0`）を疑似開始、`Stop`（`fullyIdle`）を疑似終了、`PreToolUse`（`run_command` の `args.Cwd`）でCWD更新。PreToolUseは `{"decision":"allow"}`、Stop/PreInvocationは `{}`
- Kilo: TS の `event` hook が `session.created` / `session.deleted` / `session.updated` を検知して `.py` を spawn（`pid_source: "host"`、`session.idle` は終了扱いしない）

レジストリの場所（`AGENT_SESSIONS_DIR`）と一覧コマンド `agent-sessions`（永続表示 `--watch` を含む）は [agent-compat/agent-tooling/README.md](../../README.md) の「Agent Sessions」を参照。

### テスト

`just --justfile agent-compat/agent-tooling/justfile test`（実エージェントは起動しない）。

- 探索結果がソースと generated で一致すること
- generated の shebang の次がエントリ docstring であること、`from .` / `from agent_tooling.` / 非 stdlib import が残っていないこと（`test_generated_matches_builder_contract`。lefthook の `generate-check` と二重にしない）
- `catalog.json` が `hook.yaml` と `ENTRIES` に一致し、参照ファイルが実在すること。`hook.yaml` の検証・seed コピー・PEP 723・インライナーの拒否条件は一時パッケージで固定する（`test_builder.py`）
- 各アダプタの stdin JSON → 探索対象ディレクトリ / stdout キー（Codex `hookSpecificOutput.additionalContext`、Claude は `permissionDecision` 無し、Cursor `additional_context`、Antigravity は PreToolUse `decision: allow` のあと PreInvocation `injectSteps`、Kilo Python は `additionalContext`、Kilo TS は spawn と `args` 非書き換え）
- `agent_sessions` は `AGENT_SESSIONS_DIR` を一時ディレクトリへ差し替え、5ツール分の start/cwd/end でファイル作成・更新・削除と `pid_source` を検証する（`test_agent_session_adapters.py`。レジストリ本体は `test_sessions_registry.py`）
