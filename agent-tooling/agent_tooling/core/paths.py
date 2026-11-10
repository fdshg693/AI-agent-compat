"""Shell command tokenization used to guess which paths a command reads."""

import os
import re

TOKEN_RE = re.compile(r"""'[^']*'|"[^"]*"|\S+""")


def strip_quotes(token):
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def tokenize(s):
    return [strip_quotes(t) for t in TOKEN_RE.findall(s)]


def split_subcommands(command):
    """Split a shell command string on unquoted ; & | and newlines."""
    parts = []
    current = []
    quote = None
    for ch in command:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            continue
        if ch in (";", "&", "|", "\n"):
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def normalize_repo_relative_path(root, raw_path):
    """Return a repository-relative POSIX path, or raise for outside paths."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("path must be a non-empty string")
    root_abs = os.path.abspath(root)
    candidate = raw_path if os.path.isabs(raw_path) else os.path.join(root_abs, raw_path)
    candidate = os.path.abspath(os.path.normpath(candidate))
    try:
        relative = os.path.relpath(candidate, root_abs)
    except ValueError as exc:
        raise ValueError(f"path is outside repository: {raw_path}") from exc
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        raise ValueError(f"path is outside repository: {raw_path}")
    return relative.replace(os.sep, "/")
