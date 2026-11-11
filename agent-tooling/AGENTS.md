## `agent-tooling/` — マルチ AI 向けのフックとコンテキスト検査

Python パッケージ `agent-tooling`（依存なし、Python 3.11+）。次の 2 つを持つ。

- エージェントフックの正本と、配布用の生成物（`agent_tooling/hooks/`）。対象は Claude Code / Codex / Cursor / Antigravity / Kilo
- CLI 2 本：`agent-context-check`（ステージした変更・指定ファイルに効く `AGENTS.md` と Claude Rule の一覧）と `agent-sessions`（動いている AI エージェントのセッション一覧）

### どこに何があるか

| パス                            | 中身                                                                                                     |
| ------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `agent_tooling/core/`           | ツールに依存しない、副作用のない処理（パス正規化・コマンド解析・glob・セッションレジストリ）             |
| `agent_tooling/sources/`        | コンテキスト検査が読む入力（該当する `AGENTS.md`、パス指定付きの Claude Rule）                           |
| `agent_tooling/checks/`         | `agent-context-check` のレポートを組み立てる処理（Git の index を読む）                                  |
| `agent_tooling/adapters/`       | エージェントごとのイベント・注入チャネルの差分（`<agent>/<scenario>.py`、Kilo は `.ts` も）              |
| `agent_tooling/hooks/`          | scenario ごとの `hook.yaml`、ビルダー、生成物。書き方は [hooks/AGENTS.md](agent_tooling/hooks/AGENTS.md) |
| `agent_tooling/cli.py`          | `agent-context-check` の入口                                                                             |
| `agent_tooling/sessions_cli.py` | `agent-sessions` の入口                                                                                  |
| `tests/`                        | エージェント本体を起動しない単体テスト                                                                   |

CLI の全オプション、環境変数（`AGENT_SESSIONS_DIR` / `AGENT_SESSIONS_TTL`）、出力形式は [README.md](README.md) にある。

### 守ること

- `agent_tooling/hooks/generated/` は生成物。手で直さず、ソースを変えて `generate` する。生成物はコミットする（配布物であり、パッケージデータでもある）
- scenario の入力は互いに独立させる。`nested_agents_md` は `AGENTS.md` だけ、`scoped_rules` は `.claude/rules/**/*.md` だけを読み、片方が無いときにもう片方へ fallback しない。`agent_sessions` はファイルを読まず、コンテキストも注入しない
- `adapters/` は `build/`・`tests/`・`generated/` を import しない。共通処理は関数単位で import する（ビルドで 1 ファイルにインライン化するので、モジュール名前空間経由の呼び出しは残らない）
- `agent-context-check` は「見直す候補」を出すだけの助言コマンド。lefthook に登録しない。自動で走るのはフックの再生成だけ
- 実行時の依存を足さない（`dependencies = []`）。`pyyaml` はビルドとテスト用の dev 依存。配布するフックで依存が要るなら、PEP 723 で宣言する

### コマンド

アンブレラのルートから実行する。

```sh
just --justfile agent-compat/agent-tooling/justfile generate        # 生成物を作り直す
just --justfile agent-compat/agent-tooling/justfile generate-check  # 生成物がソースと一致するか
just --justfile agent-compat/agent-tooling/justfile rules-check     # Claude Rule の frontmatter を検査
just --justfile agent-compat/agent-tooling/justfile test            # 単体テスト
uv run --project agent-compat/agent-tooling agent-context-check --staged
uv run --project agent-compat/agent-tooling agent-sessions
```

### フックを足す・変えたあと

1. `generate` → `test`
2. アンブレラで `just hooks-update`（アンブレラ自身）と `just sub-agent-hooks-update`（各サブモジュール）。新しい hook id をアンブレラで使うなら、ルートの `justfile` の `hooks-install` レシピにも足す
3. このフォルダは `agent-compat` サブモジュールの中。`agent-compat` でコミットしてから、アンブレラで `git add agent-compat` する

配布の経路（`registry/repo-hooks.yaml` → `skill-tools hooks install`）と設計判断は [hook-distribution](../../maintenance/docs/hook-distribution.md)。
