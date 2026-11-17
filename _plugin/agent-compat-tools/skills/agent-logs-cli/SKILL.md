---
name: agent-logs-cli
description: AI コーディングツール（Claude Code・Cursor・Cline・Kilo Code・Antigravity・Codex）がこの PC に残すローカルログを、ツールをまたいで一覧・検索・集計する `agent-logs` CLI の使い方を説明する。「前にどのツールで何をしたか探したい」「過去のセッションで特定のコマンドやファイル名が出た箇所を横断検索したい」「ツール別・モデル別・日別のセッション数やトークンを集計したい」「どのツールのログがどこにあるか確かめたい」ときに使う。個々のツールのログ形式そのものを知りたいときは各ツールの `*-logs` 知識スキル（Claude Code は claude-logs-investigate）を使う。
# 前提条件: `agent-logs` コマンドが PATH 上にあること（アンブレラのルートで `uv tool install --editable agent-compat/logs/agent-logs`）。このスキルはインストール・セットアップは一切行わない
# このスキルの設計意図は同階層の README.md 参照（人間のメンテナ向け）
meta:
  tag: []
  requires_repo_tools: agent-logs
  requires_env: none
  dependencies: none
  requires_install: uv tool install --editable agent-compat/logs/agent-logs
  requires_hooks: none
  requires_skills: claude-logs-investigate, cursor-logs, cline-logs, kilo-logs, antigravity-logs, codex-logs
  status: experimental
  description: no description
  version: 1.0.0
---

# agent-logs CLI の使い方

`agent-logs` は各 AI コーディングツールのローカルログを共通の形（Session / Event）に揃えて、一覧・検索・集計する読み取り専用の CLI。ログを書き換えず、外部へ送らない。インデックスを持たず毎回走査する。

フラグの正本は `agent-logs <subcommand> --help`。オプション表はこのスキルに転記しない。

## どのサブコマンドで何が分かるか

| 知りたいこと                                     | コマンド                                                                    |
| ------------------------------------------------ | --------------------------------------------------------------------------- |
| どのツールのログがどこにあり、何件あるか         | `agent-logs sources`                                                        |
| 最近のセッションの一覧（ツール・プロジェクト別） | `agent-logs sessions --since 7d [--tool ..] [--project ..]`                 |
| ある語・コマンド・ファイル名が出た箇所           | `agent-logs search "<語>" [--kind tool_call] [-e]`                          |
| 1 セッションの流れ                               | `agent-logs show <id>`（ID・前方一致・`<tool>:<id>`）                       |
| 件数・トークン・コストの集計                     | `agent-logs stats --by tool\|project\|model\|day\|month\|source\|tool-name` |

進め方の目安:

1. 初めての環境や「件数がおかしい」ときは `sources` で、各ツールが見つかっているか、どの場所を読んでいるか（NOTE 列）を先に確かめる。
2. 探し物は `search` で当たりを付け、出たセッション ID を `show` で開く。`search` はマッチ前後の断片だけを出す。全文は `show --full`、元のレコードは `show --json --raw`。
3. 大きな環境では `--since` を付ける（ファイルの更新時刻で先に絞るので速くなる）。
4. 後続処理に渡すなら `--json`（一覧系は NDJSON、`stats` は JSON 1 個）。

`search` はヒットが無いと終了コード 1 で終わる。エラーではない。

## 欠けている値の読み方

取れない値は `null`（表では空欄）で、0 とは区別される。ツールによって取れないものがあるので、集計の比較では次を前提にする。

- **トークン・コスト**: Cursor は取れない。Codex と Antigravity はトークンだけでコストが無い。Claude Code のサブエージェントのセッションにはコストが無い。`stats` の合計は「値があるセッションだけの合計」なので、ツール間の比較には使わない。
- **入力トークン**: `tokens_in` はキャッシュ読み出しを含まない（キャッシュ分は `tokens_cache_read`）。Kilo の `tokens_out` は reasoning を含む。
- **本文**: Antigravity は `brain/<id>/.system_generated/logs/transcript*.jsonl` がある会話だけ本文が読める。無い会話はメタデータだけでイベントが 0 件になる（`conversations/<id>.db` の protobuf は v1 では読まない）。Cursor の CLI チャットと IDE の composer はメタデータだけで、本文は agent-transcripts から読む。
- **Codex**: 実データで未検証。7 日より古い `.jsonl.zst` は Python 3.14 以上でだけ読み、それ未満では `sources` に件数だけ出る。

数え方・欠損の理由・ファイル形式の詳細は各ツールの知識スキル（`claude-logs-investigate`・`cursor-logs`・`cline-logs`・`kilo-logs`・`antigravity-logs`・`codex-logs`）が正本。CLI の結果がおかしいと思ったら、まずそちらで形式を確かめる。

## 秘密情報

ログには会話本文・ファイル内容・環境変数などが平文で入りうる。

- `show`・`search` の出力をそのまま外部（Issue・チャット・外部 API）へ貼らない。ユーザーに見せる前に、必要な部分だけに絞る。
- 件数や傾向だけが要るなら、本文を出さない `sessions`・`stats` で済ませる。
- 認証情報のファイル（`~/.claude/.credentials.json`、Codex・Kilo の `auth.json` など）は CLI も開かない。自分で開いて補わない。

## 前提条件

- `agent-logs` が PATH 上にあること。無ければこのスキルでは対処せず、`agent-compat/logs/agent-logs/README.md` のインストール手順を案内する（アンブレラ内なら `uv run agent-logs ...` でも動く）。
- ログの場所を変えているときは `AGENT_LOGS_<TOOL>_DIR` などの環境変数で上書きできる（一覧は README の「対象の場所と上書き」）。
- 読めなくなったツールがあれば、形式変更の疑いがある。直し方は `agent-compat/logs/agent-logs/AGENTS.md`。
