# Cline Personal Info Plugin

Cline のカスタムツール登録を確認するための最小プラグインです。
`get_personal_info` を呼び出すと、JSON 文字列として `toolCalled: true` と架空の個人情報を返します。

## Install

リポジトリのルートで次のコマンドを実行します。

```sh
cline plugin install ./agent-compat/formats/cline/personal-info --cwd .
```

> [!WARNING] Windows (PowerShell/cmd) で実行する場合
>
> 上記を PowerShell や cmd からそのまま実行すると、次のエラーで失敗します。
>
> ```
> error: ENOENT: no such file or directory, uv_spawn 'npm'
> ```
>
> 原因は `cline` CLI（Bun ランタイム embed）が `npm` を spawn する際、環境変数名 `PATH`（全大文字）を大文字小文字区別付きで参照するのに対し、Windows ネイティブシェルのプロセス環境では変数名が `Path`（先頭大文字）になっているため npm の解決に失敗することです（`where.exe npm` で見えていても効きません）。
>
> このリポジトリでは Git Bash 経由で実行する回避手段を用意しています。リポジトリルートで:
>
> ```powershell
> just cline-personal-info
> ```
>
> または Git Bash を直接呼び出して:
>
> ```powershell
> & "C:/Program Files/Git/bin/bash.exe" -c "cline plugin install ./agent-compat/formats/cline/personal-info --force"
> ```
>
> 詳細は [`docs/integrations/cline.md`](../../../../docs/integrations/cline.md) を参照してください。
>
> さらに、すでに別の `cline` hub-daemon（VS Code の Cline 拡張や以前の失敗した install 試行の常駐プロセス）がポート `127.0.0.1:25463` を占有していると、今度は `Failed to start hub server ... EADDRINUSE` で失敗します。この場合は Cline を動かしているエディタ/IDE を閉じて `cline` プロセスが 0 件になったことを確認してから再実行してください。

このリポジトリでは、動作確認のため実際のインストールは行っていません。

## Check

Cline に次のように依頼すると、`get_personal_info` が利用されます。

```text
get_personal_info ツールを呼び出して、toolCalled の値を教えてください。
```

返却される個人情報はすべて架空のテストデータです。
