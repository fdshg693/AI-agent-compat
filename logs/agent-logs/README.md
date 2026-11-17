# agent-logs

AI コーディングツールがローカルに残すログを、ツールをまたいで一覧・検索・集計する CLI。読み取り専用で、ログを書き換えず、外部へ送らない。

対象: Claude Code・Cursor・Cline・Kilo Code・Antigravity・Codex（Codex は仕様とフィクスチャだけで実装し、実データでは未検証）。GitHub Copilot は未対応。

## インストール

Python 3.11 以上。実行時の依存は無い。

```sh
uv tool install --editable agent-compat/logs/agent-logs   # アンブレラのルートから
# または
just --justfile agent-compat/logs/agent-logs/justfile install
```

インストールせずに使うなら `uv run --project agent-compat/logs/agent-logs agent-logs ...`（アンブレラの uv workspace に入っているので `uv run agent-logs ...` でも動く）。

## 使い方

```sh
agent-logs sources                              # ツールごとのログの場所・有無・件数・最終更新
agent-logs sessions --since 7d                  # セッション一覧（新しい順、既定 50 件）
agent-logs sessions --tool claude,kilo --project ai/tools --json
agent-logs show 1a2b3c                          # 1 セッションの正規化イベント（ID・前方一致・<tool>:<id>）
agent-logs show claude:1a2b3c --kind tool_call --json --raw
agent-logs search "uv sync"                     # 本文とツール呼び出しの横断検索（大文字小文字を区別しない）
agent-logs search "Edit|Write" -e --kind tool_call --since 3d
agent-logs stats --by model --since 30d         # 集計（tool / project / model / day / month / source / tool-name）
```

### 共通フィルタ

| オプション                   | 意味                                                                                   |
| ---------------------------- | -------------------------------------------------------------------------------------- |
| `--tool a,b`                 | 対象ツール（`claude`・`cursor`・`cline`・`kilo`・`antigravity`・`codex`）              |
| `--since` / `--until`        | ISO 日付・日時（タイムゾーン無しはローカル時刻）か相対指定（`30m`・`12h`・`7d`・`2w`） |
| `--project`                  | プロジェクトのパスの部分一致。大文字小文字・`\`/`/`・ドライブレターの違いを無視する    |
| `--role`（`search`・`show`） | `user`・`assistant`・`system`・`tool`                                                  |
| `--json`                     | 一覧系（`sources`・`sessions`・`show`・`search`）は NDJSON、`stats` は JSON 1 個       |

`search` はマッチの前後だけを出す（`--width`、既定 120 文字）。全文は `show` で、元のレコードは `show --json --raw` で見る。ヒットが無いと終了コード 1。

各ツールの読み取りに失敗しても、警告を stderr に出して他のツールは続ける。

## 正規化スキーマ

- **Session**: `id, tool, source, project, cwd, started_at, ended_at, model, title, parent_id, message_count, tool_call_count, tokens_in, tokens_out, tokens_cache_read, tokens_cache_write, cost, path`
- **Event**: `session_id, tool, ts, role, kind, tool_name, call_id, text, model, tokens_*, cost`（`--raw` で `raw`）
- `kind`: `message`・`reasoning`・`tool_call`・`tool_result`・`system`・`summary`・`usage`・`turn_end`・`raw`（未知のレコード）
- 取れない値は `null`（0 と区別する）。時刻は UTC の ISO 8601。`project` はパスを正規化したもの（`C:/Users/...`）。
- `tokens_in` はキャッシュ読み出しを含まない入力（キャッシュ分は `tokens_cache_read`）。入力にキャッシュを含めて記録するツール（Codex・Cline の SDK セッション）は差し引いて揃える。Kilo の `tokens_out` は reasoning を含む。
- トークンは 1 応答につき 1 回だけ数える。セッション合計はツール自身の累計値があればそれを使う（ツールごとの詳細は各アダプタの docstring）。

## 対象の場所と上書き

| ツール      | 既定の場所                                                                                                    | 上書き                                               |
| ----------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| claude      | `~/.claude/projects/`                                                                                         | `AGENT_LOGS_CLAUDE_DIR`・`CLAUDE_CONFIG_DIR`         |
| cursor      | `~/.cursor/projects/*/agent-transcripts/`（補完に `~/.cursor/chats/`・`%APPDATA%/Cursor/User/globalStorage`） | `AGENT_LOGS_CURSOR_DIR`                              |
| cline       | `~/.cline/data/`・`%APPDATA%/Code/User/globalStorage/saoudrizwan.claude-dev/`                                 | `AGENT_LOGS_CLINE_DIR`・`CLINE_DATA_DIR`             |
| kilo        | `~/.local/share/kilo/kilo.db`                                                                                 | `AGENT_LOGS_KILO_DIR`                                |
| antigravity | `~/.gemini/{antigravity,antigravity-cli,antigravity-ide}/`                                                    | `AGENT_LOGS_ANTIGRAVITY_DIR`（`~/.gemini` の代わり） |
| codex       | `~/.codex/sessions/`・`archived_sessions/`                                                                    | `AGENT_LOGS_CODEX_DIR`・`CODEX_HOME`                 |

`AGENT_LOGS_HOME` はホームディレクトリ全体を、`AGENT_LOGS_APPDATA` は `%APPDATA%`（macOS は `~/Library/Application Support`、Linux は `~/.config`）を置き換える。テストはこの 2 つでフィクスチャを指す。

## 注意

- ログには会話本文・ファイル内容・環境変数などの秘密情報が平文で入りうる。`show`・`search` の出力を共有するときは中身を確認する。認証情報のファイル・表（`~/.claude/.credentials.json`、Cline の `secrets.json`、Kilo の `auth.json`・認証系の表、Codex の `auth.json` など）は開かない。
- インデックスを持たず毎回走査する。`--since` はファイルの更新時刻での事前の絞り込みにも使うので、大きな環境では付けると速い。
- SQLite は `mode=ro` で開く（Antigravity は一時コピーを読む）。
- Codex の 7 日より古い rollout（`.jsonl.zst`）は Python 3.14 以上でだけ読む。それ未満では件数を `sources` に出して読み飛ばす。
- ログ形式は各ツールで非公開のことが多く、バージョンで変わる。読めなくなったら [AGENTS.md](AGENTS.md) の手順で直す。

## 開発

```sh
just --justfile agent-compat/logs/agent-logs/justfile test
```

構成・規約・アダプタの追加手順は [AGENTS.md](AGENTS.md)。
