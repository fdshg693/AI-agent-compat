"""通知に出すプロジェクト名の解決（どのセッションからの通知かを見分けるため）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

UNKNOWN_PROJECT_TITLE = "unknown"


def resolve_project_title(
    project_dir: str | None = None,
    *,
    anchor: Path | None = None,
    marker: str | None = None,
) -> str:
    """プロジェクトのフォルダ名を返す。例外を外に出さない。優先順位:

    1. `project_dir`（呼び出し側が渡す。Claude なら `CLAUDE_PROJECT_DIR`）
    2. `git rev-parse --show-toplevel`
    3. `anchor` から上位ディレクトリを辿り、`marker` フォルダを持つ最初のディレクトリ
    4. どれも失敗したら "unknown"
    """
    if project_dir and project_dir.strip():
        name = Path(project_dir.strip()).name
        if name:
            return name

    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=creationflags,
        )
        if result.returncode == 0:
            name = Path(result.stdout.strip()).name
            if name:
                return name
    except Exception:
        pass

    if anchor is not None and marker:
        try:
            for ancestor in Path(anchor).resolve().parents:
                if (ancestor / marker).is_dir():
                    return ancestor.name
        except Exception:
            pass

    return UNKNOWN_PROJECT_TITLE
