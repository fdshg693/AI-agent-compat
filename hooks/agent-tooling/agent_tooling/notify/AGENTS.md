## `notify/` — 端末種別ごとの通知（音・視覚通知）

各エージェントのアダプタ（現在は `../adapters/claude/stop_alert.py` と scenario `notify` の `../adapters/claude/notify.py`・`../adapters/codex/notify.py`・`../adapters/kilo/notify.py`）から呼ぶ通知の共通処理。フック本体ではなく、ビルドでフックの成果物へインライン化される（`from agent_tooling.notify import …`）。

### 責務の境界

- **環境変数・`.env`・`hook_dir()` を読まない。** 設定値（鳴らすファイル、有効/無効、文言、秒数、プロジェクト名、再実行するエントリ）はすべて引数で受け取る。`STOP_ALERT_*` や `.env` の解決はアダプタ側の約束事
- **例外を外に出さない。stdout に書かない。** フックの stdout はエージェントが解釈する。失敗は戻り値で表す
- 戻り値は `ok`／`mode`（／`detail`）を持つ dict。アダプタはそのままログ（`logs/<hook id>/`）へ書き、テストもこの形に依存する
- 判定順は「OS（表に無ければ `unsupported`）→ 有効/無効（`disabled`）→ バックエンド」
- どのイベントで出すか・文言・アプリ名はアダプタが決める。`notify/` は投稿・整形だけ

### 構成

- `__init__.py` — 公開 API（`notify_sound`・`notify_popup`・`run_notify_popup`・`notify_post`・`notify_remove`・`resolve_project_title`・`truncate_body`・`shorten_home`・`format_title`・`mac_helper_app`・`notify_state_dir`・`notify_suppression`・`suppression_reason`）と、`sys.platform` → バックエンドの表
- `windows.py` — winsound／winreg の音と tkinter のポップアップ（子プロセスで描く。Win32 API は `ctypes`）。同じセッションの古い窓の置き換えと、スヌーズ・消音のボタンもここ
- `state.py` — 抑止（スヌーズ・消音）の状態ファイルの読み書きと判定。OS 非依存。トップレベル名は `_state_` 接頭辞
- `macos.py` — 通知センターへの通知（Swift ヘルパー → osascript）と afplay の音。identifier 付きの投稿・削除（`_mac_post`・`_mac_remove`）もここ
- `macos_helper/` — 通知ヘルパーのソース（`main.swift`・`Info.plist.in`）と `build.sh`。Python ではないのでインライン化されない
- `project.py` — 通知に出すプロジェクト名（引数 → git → `anchor` から上の `marker` → `unknown`）
- `text.py` — 本文の整形（空白を潰して 120 文字に切り詰める）、ホームの `~` 置き換え、タイトル `<label> [<cwd のフォルダ名>]`（`format_title`）

### 対応 OS と仕組み

| OS                 | 音（`notify_sound`）                                                        | 視覚通知（`notify_popup`）                                                                                   |
| ------------------ | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Windows（`win32`） | `sound_path` の WAV を winsound で同期再生。無い・失敗ならビープ／トーン    | `entry_script` を `popup_flag` 付きで再実行し、子プロセスが tkinter で描く（下の「Windows のポップアップ」） |
| macOS（`darwin`）  | `sound_path`（無ければ `Glass.aiff`）を afplay で鳴らす。切り離して待たない | 通知センターへ同期で出す（上限 6 秒）。タイトル＝`project`、サブタイトル＝`subtitle`。`seconds` は使わない   |
| その他             | `unsupported`                                                               | `unsupported`                                                                                                |

### Windows のポップアップ

- タイトルバー付きの通常の窓。最小化（タスクバーに残る）・リサイズ・最大化ができ、表示位置は画面右下。× か「閉じる」で閉じ、`seconds` 経つと自動で閉じる。最小化したら自動クローズのタイマーを止め、復元しても再開しない
- **フォーカスを奪わない。** Tk は外枠を作った瞬間に（非表示のまま）フォアグラウンドを取るので、`tk.Tk()` より前に `LockSetForegroundWindow(LSFW_LOCK)` を呼び、表示後に必ず解除する。拡張スタイルは `WS_EX_NOACTIVATE | WS_EX_APPWINDOW`（`WS_EX_NOACTIVATE` だけだとタスクバーから消える）、表示は `SW_SHOWNOACTIVATE`、最前面は `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE)`。`-toolwindow` など外枠を作り直す Tk 属性は使わない（取得した HWND が無効になる）
- 子プロセスの argv は `popup_flag text seconds project session_id state_dir`（空は `""`）。`run_notify_popup(text, seconds, project, app_name, *, session_id, state_dir)` が受ける。窓の例外は握りつぶさない（手で `--popup` を実行したときに見えるように。子プロセスの出力は捨てている）
- **置き換え**: `state_dir/popup-<session_id>.json`（子プロセス自身の pid と起動時刻）を見て、同じセッションの古い窓のプロセスを終了してから出す。pid 再利用で無関係なプロセスを終了しないよう起動時刻の一致を確かめる。`session_id` か `state_dir` が空なら置き換えない
- **スヌーズ・消音のボタン**: 「15分スヌーズ」「1時間スヌーズ」（全体。押すと窓を閉じる）、「このセッションを消音」（`session_id` が無いと押せない）「すべて消音（今日中）」「解除」（窓は残す）。抑止中は状態の行に残り時間を出す（30 秒ごとに更新）。`state_dir` が無ければボタンを出さない

### 抑止の状態ファイル（`state.py`）

- 置き場所は `<state_dir>/state.json`。既定の `state_dir` は `notify_state_dir(local_app_data)` ＝ `<LOCALAPPDATA>/agent-tooling/notify`（`LOCALAPPDATA` の値は呼び出し元が読んで渡す）。フックの配置先・エージェント（Claude・Kilo）によらず 1 つ
- 形: `{"version": 1, "global": {"snooze_until": <epoch 秒>, "mute_until": <epoch 秒>}, "sessions": {"<session_id>": {同じ形}}}`。期限付きの値だけを持ち、解除＝値を消す、期限切れ＝無視（書き込み時に掃除）。セッションの抑止は最長 12 時間（`_STATE_SESSION_MAX_SECONDS`）
- スヌーズ＝音も窓も出さない、消音＝音だけ止める。書き込みは一時ファイル + `os.replace`。読めない・壊れた・版が違うファイルは「抑止なし」
- `notify_suppression(state_dir, session_id)` は `{"snooze": {"scope", "until"} | None, "mute": 同じ形 | None}` を返す。`_POPUP_WINDOWS` にある OS（Windows）だけで判定し、それ以外の OS・`state_dir` 無し・例外は抑止なし。`notify_sound`／`notify_popup` の `enabled` への合成はアダプタが行う（判定順を崩さないため）。`suppression_reason()` はログ用の 1 語（例 `mute:session`）
- 書き込み・解除（`_state_set`・`_state_clear`）は窓だけが使うので公開 API にしない

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

ヘルパーの既定の置き場所は `~/Library/Application Support/agent-tooling/notify/<Name>.app`（`mac_helper_app()`）。フックの配置先（プロジェクト・グローバル）によらず 1 つで済ませるため。ビルドと LaunchServices への登録は `just --justfile agent-compat/hooks/agent-tooling/justfile notify-helper-mac <claude|codex|kilo>`、初回だけ `<Name>.app/Contents/MacOS/<Name> authorize` を手動で実行して許可する。バンドル ID は既定で `local.agent-tooling.<agent>-notify`（`bundle_prefix` で変えられる）。終了コードは `main.swift` と `macos.py` で合わせる（0 成功・1 その他・2 未決定・3 拒否）

### バックエンド（OS）を足す

1. `<os>.py` を足す。トップレベル名はすべて OS 名の接頭辞付きにする（`_win_…`／`_mac_…`）。インライン化でトップレベル名が 1 つの名前空間に平坦化され、同名はビルドエラーになる
2. `__init__.py` の表に 1 行ずつ足す。`_SOUND_BACKENDS` と `_POPUP_SPAWNERS` の OS 集合は揃える（テストで検査）。`_POPUP_WINDOWS` は視覚通知を子プロセスで描く OS だけが持つ。スポナーは `(text, seconds, project, entry_script, popup_flag, *, subtitle, notification_id, helper_app, session_id, state_dir)` を受け、使わない引数は無視する（macOS は `session_id`・`state_dir` を `**_win_only` で受け流す）
3. バックエンドのモジュールは `__init__.py` の最上位で import する。関数内の `agent_tooling`／相対 import はビルドエラー。OS 依存の標準ライブラリ（`winsound`・`winreg`・`tkinter` など）だけを関数内で import する
4. `subprocess.CREATE_NO_WINDOW` などの Windows 専用属性は `sys.platform == "win32"` でガードする
5. `../../tests/test_notify.py` に振り分けと分岐のテストを足す（実際の音・ウィンドウは出さず、モジュールや `Popen` を差し替える）

### ビルド上の注意

- 子プロセスで描く視覚通知（Windows）は、インライン化後このモジュールのファイルが配置先に無いため、呼び出し側が渡す `entry_script`（`sys.argv[0]`）を `popup_flag` 付きで再実行する。argv の分岐はエントリ側に置く
- 変えたら `just --justfile agent-compat/hooks/agent-tooling/justfile generate` で `../hooks/generated/` を再生成し、`test`・`generate-check` を通す
