## `agent-logs/` — AI コーディングツールのローカルログの検索・集計

Python パッケージ `agent-logs`（依存なし、Python 3.11+）、コマンド `agent-logs`。使い方は [README.md](README.md)。

### どこに何があるか

| パス                              | 中身                                                                                             |
| --------------------------------- | ------------------------------------------------------------------------------------------------ |
| `agent_logs/model.py`             | 正規化スキーマ（`Session`・`Event`・`SourceInfo`・`Filters`）                                    |
| `agent_logs/adapters/base.py`     | アダプタの契約（`detect()`・`iter_sessions(filters)`・`iter_events(session)`）                   |
| `agent_logs/adapters/<tool>.py`   | ツールごとの読み取り。docstring に正本の知識スキルと、トークンの数え方などの判断を書く           |
| `agent_logs/adapters/__init__.py` | アダプタの登録簿                                                                                 |
| `agent_logs/paths.py`             | ルートの解決（`AGENT_LOGS_HOME` ほか）、パス正規化、Junction を辿らない走査                      |
| `agent_logs/readers.py`           | JSONL のストリーム読み、JSON、読み取り専用の SQLite                                              |
| `agent_logs/timeutil.py`          | 時刻の正規化（ISO・epoch・protobuf・Cursor の `<timestamp>` タグ）                               |
| `agent_logs/query.py`・`stats.py` | フィルタ・検索・集計（アダプタを横断）                                                           |
| `agent_logs/cli.py`               | サブコマンドと出力                                                                               |
| `tests/fixtures/<tool>/`          | 架空のログ。`home/` が `~`、`appdata/` が `%APPDATA%` に当たる。SQLite は `<name>.db.sql` で置く |

### 守ること

- **読み取り専用・外部送信なし。** ログのある場所に何も書かない（SQLite は `readers.open_sqlite` で開く。`-wal`/`-shm` が増える疑いがあるツールは `mode="copy"`）。ネットワークを使わない。
- **認証情報を開かない。** 各アダプタの docstring に読まないファイル・表・フィールドを書き、テストで確かめる。
- **フィクスチャに実ログを入れない。** 値はすべて架空（ユーザー名は `alice` など）。このサブモジュールは公開リポジトリ。実データで分かったことは構造だけを知識スキルに書く。
- SQLite のバイナリをコミットしない。`<name>.db.sql` を置けば `tests/conftest.py` がテスト時に `<name>.db` を作る。
- **仕様の正本は知識スキル。** アダプタの docstring・このファイルに形式の説明を重複させない。形式が変わったら先に知識スキルを直す。
- 1 アダプタ・1 ファイルの失敗で全体を止めない（`self.warn` して続ける）。取れない値は `None`（0 にしない）。
- パッケージの中で Junction・symlink を辿らない（`paths.walk_files`・`list_dir`）。
- 実行時の依存を足さない（`dependencies = []`）。agent-tooling にも依存しない。
- テストは実ログを読まない。`fixture_home("<tool>")` が `AGENT_LOGS_HOME`・`AGENT_LOGS_APPDATA` をフィクスチャに向け、ツール固有の環境変数を消す。

### アダプタを足す・直す手順

1. 知識スキル（`skills/plugins/ai-tools-knowledge/skills/<tool>-logs/`、Claude Code は `cc-knowledge/skills/claude-logs-investigate/`）に所在・形式・秘密情報・トークンの数え方を書く（`skills` サブモジュールでコミット）。
2. `agent_logs/adapters/<tool>.py` を書き、`adapters/__init__.py` に登録する。
3. `tests/fixtures/<tool>/` に架空のフィクスチャを作る（秘密情報が出ないことを確かめるための偽の値も入れる）。
4. `tests/test_<tool>.py` を書き、`just --justfile agent-compat/logs/agent-logs/justfile test`。
5. 実機で `agent-logs sources --tool <tool>`・`sessions`・`stats` を流し、件数・警告・所要時間を確かめる（本文を記録・共有しない）。
6. README の「対象の場所と上書き」を更新する。

### コマンド

アンブレラのルートから実行する。

```sh
just --justfile agent-compat/logs/agent-logs/justfile test
just --justfile agent-compat/logs/agent-logs/justfile run sources
uv run agent-logs sessions --since 1d
```

このフォルダは `agent-compat` サブモジュールの中。`agent-compat` でコミットしてから、アンブレラで `git add agent-compat` する。
