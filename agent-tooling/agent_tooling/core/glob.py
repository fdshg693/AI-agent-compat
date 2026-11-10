"""Side-effect-free glob matching for repository-relative POSIX paths."""

from __future__ import annotations

import re


def glob_regex(pattern: str) -> re.Pattern[str]:
    pattern = pattern.replace("\\", "/")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    result: list[str] = ["^"]
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                i += 2
                if i < len(pattern) and pattern[i] == "/":
                    result.append("(?:.*/)?")
                    i += 1
                else:
                    result.append(".*")
                continue
            result.append("[^/]*")
        elif char == "?":
            result.append("[^/]")
        elif char == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                result.append(r"\[")
            else:
                content = pattern[i + 1 : end]
                if content.startswith("!"):
                    content = "^" + content[1:]
                result.append("[" + content + "]")
                i = end
        else:
            result.append(re.escape(char))
        i += 1
    result.append("$")
    return re.compile("".join(result))


def match_path(pattern: str, path: str) -> bool:
    """Match a glob against a repository-relative POSIX path."""
    return glob_regex(pattern).fullmatch(path.replace("\\", "/")) is not None
