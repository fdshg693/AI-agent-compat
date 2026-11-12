#!/bin/sh
# 通知ヘルパー <Name>.app をビルドし、LaunchServices に登録する（macOS のみ）。
#
#   build.sh <Name> <BundleID> <出力先ディレクトリ>
#   例: build.sh ClaudeNotify local.agent-tooling.claude-notify "$HOME/Library/Application Support/agent-tooling/notify"
#
# 通常は agent-tooling の justfile の notify-helper-mac レシピから呼ぶ。
# 送信元の名前と通知の許可はバンドルごとに分かれるので、エージェントごとに別の .app を作る。
# 初回はビルド後に `<出力先>/<Name>.app/Contents/MacOS/<Name> authorize` を手動で 1 回実行して許可する。
set -eu

if [ "$#" -ne 3 ]; then
    echo "usage: $0 <Name> <BundleID> <dest-dir>" >&2
    exit 2
fi
if [ "$(uname -s)" != "Darwin" ]; then
    echo "$0: macOS 専用です" >&2
    exit 1
fi

name=$1
bundle_id=$2
dest=$3
src=$(cd "$(dirname "$0")" && pwd)
app="$dest/$name.app"
lsregister=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister

rm -rf "$app"
mkdir -p "$app/Contents/MacOS"
sed -e "s/@HELPER_NAME@/$name/g" -e "s/@HELPER_BUNDLE_ID@/$bundle_id/g" \
    "$src/Info.plist.in" >"$app/Contents/Info.plist"
swiftc -O -target "$(uname -m)-apple-macos13" "$src/main.swift" -o "$app/Contents/MacOS/$name"
xattr -cr "$app"
codesign --force -s - "$app"
"$lsregister" -f "$app"

echo "built: $app"
echo "初回のみ: \"$app/Contents/MacOS/$name\" authorize"
