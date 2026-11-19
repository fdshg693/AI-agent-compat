"""通知に出す文字列の整形（OS によらない）。"""

from __future__ import annotations

import os

# 本文の最大文字数。超えた分は「…」に置き換える（通知センターで読める長さに抑える）
MAX_BODY_CHARS = 120


def truncate_body(text: str, limit: int = MAX_BODY_CHARS) -> str:
    """改行・連続する空白を 1 つの空白に潰し、`limit` 文字に切り詰める。"""
    collapsed = " ".join(text.split())
    if len(collapsed) > limit:
        return collapsed[:limit] + "…"
    return collapsed


def shorten_home(path: str) -> str:
    """ホームディレクトリ配下のパスを `~` 始まりにする（どのセッションか見分けるサブタイトル用）。"""
    if not path:
        return ""
    home = os.path.expanduser("~")
    if home and home != "~" and (path == home or path.startswith(home + os.sep)):
        return "~" + path[len(home) :]
    return path


def format_title(label: str, cwd: str) -> str:
    """`<label> [<cwd のフォルダ名>]`。どのプロジェクトの通知かをタイトルで見分ける。"""
    name = os.path.basename(os.path.normpath(cwd)) if cwd else "."
    return f"{label} [{name or cwd}]"
