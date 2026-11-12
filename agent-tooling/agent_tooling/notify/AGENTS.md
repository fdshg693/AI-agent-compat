## `notify/` — 端末種別ごとの通知（音・視覚通知）

各エージェントのアダプタ（現在は `../adapters/claude/stop_alert.py` と scenario `notify` の `../adapters/claude/notify.py`）から呼ぶ通知の共通処理。フック本体ではなく、ビルドでフックの成果物へインライン化される（`from agent_tooling.notify import …`）。

### 責務の境界

- **環境変数・`.env`・`hook_dir()` を読まない。** 設定値（鳴らすファイル、有効/無効、文言、秒数、プロジェクト名、再実行するエントリ）はすべて引数で受け取る。`STOP_ALERT_*` や `.env` の解決はアダプタ側の約束事
- **例外を外に出さない。stdout に書かない。** フックの stdout はエージェントが解釈する。失敗は戻り値で表す
- 戻り値は `ok`／`mode`（／`detail`）を持つ dict。アダプタはそのままログ（`logs/<hook id>/`）へ書き、テストもこの形に依存する
- 判定順は「OS（表に無ければ `unsupported`）→ 有効/無効（`disabled`）→ バックエンド」
- どのイベントで出すか・文言・アプリ名はアダプタが決める。`notify/` は投稿・整形だけ

### 構成

- `__init__.py` — 公開 API（`notify_sound`・`notify_popup`・`run_notify_popup`・`notify_post`・`notify_remove`・`resolve_project_title`・`truncate_body`・`shorten_home`・`format_title`・`mac_helper_app`）と、`sys.platform` → バックエンドの表
- `windows.py` — winsound／winreg の音と tkinter のポップアップ（子プロセスで描く）
- `macos.py` — 通知センターへの通知（Swift ヘルパー → osascript）と afplay の音。identifier 付きの投稿・削除（`_mac_post`・`_mac_remove`）もここ
- `macos_helper/` — 通知ヘルパーのソース（`main.swift`・`Info.plist.in`）と `build.sh`。Python ではないのでインライン化されない
- `project.py` — 通知に出すプロジェクト名（引数 → git → `anchor` から上の `marker` → `unknown`）
- `text.py` — 本文の整形（空白を潰して 120 文字に切り詰める）、ホームの `~` 置き換え、タイトル `<label> [<cwd のフォルダ名>]`（`format_title`）

### 対応 OS と仕組み

| OS                 | 音（`notify_sound`）                                                        | 視覚通知（`notify_popup`）                                                                                 |
| ------------------ | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Windows（`win32`） | `sound_path` の WAV を winsound で同期再生。無い・失敗ならビープ／トーン    | `entry_script` を `popup_flag` 付きで再実行し、子プロセスが tkinter で描く。`seconds` で自動で閉じる       |
| macOS（`darwin`）  | `sound_path`（無ければ `Glass.aiff`）を afplay で鳴らす。切り離して待たない | 通知センターへ同期で出す（上限 6 秒）。タイトル＝`project`、サブタイトル＝`subtitle`。`seconds` は使わない |
| その他             | `unsupported`                                                               | `unsupported`                                                                                              |

identifier 付きで出す・消す API（scenario `notify` が使う）:

| API                                                                         | macOS                                                                                               | その他（Windows を含む） |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------ |
| `notify_post(title, subtitle, body, *, sound, notification_id, helper_app)` | 下の順で出す。`body` はここで整形する。`sound` は通知の音の名前（`Glass`・`Hero` など。空なら無音） | `unsupported`            |
| `notify_remove(notification_id, *, helper_app, timeout)`                    | ヘルパーの `remove --id`。ヘルパーが無いと消せない（`helper_missing`）。`timeout` 省略時は 6 秒     | `unsupported`            |

Windows のポップアップは別プロセスで後から消せないので、この 2 つの表（`_POST_BACKENDS`・`_REMOVE_BACKENDS`）には載せない。両表の OS 集合は揃える（テストで検査）。`notify_popup` と違い有効/無効の引数は無い（フックを登録するかどうかで決める）

macOS の通知は次の順に試す。

1. `notification_id` があり、`helper_app`（`<Name>.app`）の中に実行ファイルがあれば `post --id …`。同じ id の通知は置き換わる
2. ヘルパーの終了コードが 3（ユーザーが拒否）なら何もしない。それ以外の失敗（無い・未決定・エラー・タイムアウト）なら osascript（値は argv で渡す）で出す。結果の `helper` に失敗理由を残す
3. `notification_id` が空なら最初から osascript。osascript は許可が無くても終了コード 0 なので、`mode: osascript` は「出た」とは限らない

ヘルパーの既定の置き場所は `~/Library/Application Support/agent-tooling/notify/<Name>.app`（`mac_helper_app()`）。フックの配置先（プロジェクト・グローバル）によらず 1 つで済ませるため。ビルドと LaunchServices への登録は `just --justfile agent-compat/agent-tooling/justfile notify-helper-mac <claude|codex|kilo>`、初回だけ `<Name>.app/Contents/MacOS/<Name> authorize` を手動で実行して許可する。バンドル ID は既定で `local.agent-tooling.<agent>-notify`（`bundle_prefix` で変えられる）。終了コードは `main.swift` と `macos.py` で合わせる（0 成功・1 その他・2 未決定・3 拒否）

### バックエンド（OS）を足す

1. `<os>.py` を足す。トップレベル名はすべて OS 名の接頭辞付きにする（`_win_…`／`_mac_…`）。インライン化でトップレベル名が 1 つの名前空間に平坦化され、同名はビルドエラーになる
2. `__init__.py` の表に 1 行ずつ足す。`_SOUND_BACKENDS` と `_POPUP_SPAWNERS` の OS 集合は揃える（テストで検査）。`_POPUP_WINDOWS` は視覚通知を子プロセスで描く OS だけが持つ。スポナーは `(text, seconds, project, entry_script, popup_flag, *, subtitle, notification_id, helper_app)` を受け、使わない引数は無視する
3. バックエンドのモジュールは `__init__.py` の最上位で import する。関数内の `agent_tooling`／相対 import はビルドエラー。OS 依存の標準ライブラリ（`winsound`・`winreg`・`tkinter` など）だけを関数内で import する
4. `subprocess.CREATE_NO_WINDOW` などの Windows 専用属性は `sys.platform == "win32"` でガードする
5. `../../tests/test_notify.py` に振り分けと分岐のテストを足す（実際の音・ウィンドウは出さず、モジュールや `Popen` を差し替える）

### ビルド上の注意

- 子プロセスで描く視覚通知（Windows）は、インライン化後このモジュールのファイルが配置先に無いため、呼び出し側が渡す `entry_script`（`sys.argv[0]`）を `popup_flag` 付きで再実行する。argv の分岐はエントリ側に置く
- 変えたら `just --justfile agent-compat/agent-tooling/justfile generate` で `../hooks/generated/` を再生成し、`test`・`generate-check` を通す
