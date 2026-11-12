## `notify/` — 端末種別ごとの通知（音・視覚通知）

各エージェントのアダプタ（現在は `../adapters/claude/stop_alert.py`）から呼ぶ通知の共通処理。フック本体ではなく、ビルドでフックの成果物へインライン化される（`from agent_tooling.notify import …`）。

### 責務の境界

- **環境変数・`.env`・`hook_dir()` を読まない。** 設定値（鳴らすファイル、有効/無効、文言、秒数、プロジェクト名、再実行するエントリ）はすべて引数で受け取る。`STOP_ALERT_*` や `.env` の解決はアダプタ側の約束事
- **例外を外に出さない。stdout に書かない。** フックの stdout はエージェントが解釈する。失敗は戻り値で表す
- 戻り値は `ok`／`mode`（／`detail`）を持つ dict。アダプタはそのままログ（`logs/<hook id>/`）へ書き、テストもこの形に依存する
- 判定順は「OS（表に無ければ `unsupported`）→ 有効/無効（`disabled`）→ バックエンド」
- どのイベントで出すか・文言・アプリ名はアダプタが決める。`notify/` は投稿・整形だけ

### 構成

- `__init__.py` — 公開 API（`notify_sound`・`notify_popup`・`run_notify_popup`・`resolve_project_title`）と、`sys.platform` → バックエンドの表
- `windows.py` — winsound／winreg の音と tkinter のポップアップ（子プロセスで描く）
- `project.py` — 通知に出すプロジェクト名（引数 → git → `anchor` から上の `marker` → `unknown`）

### バックエンド（OS）を足す

1. `<os>.py` を足す。トップレベル名はすべて OS 名の接頭辞付きにする（`_win_…`／`_mac_…`）。インライン化でトップレベル名が 1 つの名前空間に平坦化され、同名はビルドエラーになる
2. `__init__.py` の 3 つの表（`_SOUND_BACKENDS`・`_POPUP_SPAWNERS`・`_POPUP_WINDOWS`）に 1 行ずつ足す。表の OS 集合は揃える（テストで検査）
3. バックエンドのモジュールは `__init__.py` の最上位で import する。関数内の `agent_tooling`／相対 import はビルドエラー。OS 依存の標準ライブラリ（`winsound`・`winreg`・`tkinter` など）だけを関数内で import する
4. `subprocess.CREATE_NO_WINDOW` などの Windows 専用属性は `sys.platform == "win32"` でガードする
5. `../../tests/test_notify.py` に振り分けと分岐のテストを足す（実際の音・ウィンドウは出さず、モジュールや `Popen` を差し替える）

### ビルド上の注意

- 子プロセスで描く視覚通知は、インライン化後このモジュールのファイルが配置先に無いため、呼び出し側が渡す `entry_script`（`sys.argv[0]`）を `popup_flag` 付きで再実行する。argv の分岐はエントリ側に置く
- 変えたら `just --justfile agent-compat/agent-tooling/justfile generate` で `../hooks/generated/` を再生成し、`test`・`generate-check` を通す
