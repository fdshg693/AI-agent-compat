"""Contract for the scoped-rules hook scenario.

The Claude Rule ``paths`` field remains a list of glob/file patterns.  This
scenario may add technical filtering with ``FILE_REGEXES``; those expressions
are evaluated with ``re.fullmatch`` against a repository-relative POSIX path,
never with ``re.search``.  An empty tuple means that no additional filter is
applied, and multiple expressions are an AND filter.
"""

from __future__ import annotations

SCENARIO_ID: str = "scoped-rules"
MATCHER_VERSION: str = "1"
RULES_DIRECTORY: str = ".claude/rules"
REQUIRE_PATHS: bool = True
FILE_REGEXES: tuple[str, ...] = ()
