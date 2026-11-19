"""Shared hook-script boilerplate: UTF-8 stdio, JSON stdin, log/finish.

Every hook script's `main()` starts with the same handful of steps before its
own tool-specific logic begins: force UTF-8 stdio, resolve whether debug
logging is on, read+parse the JSON payload from stdin (falling through
quietly on bad input), and set up a `log` dict plus a `finish()` closure that
writes the debug log (if enabled) and exits. This module extracts that shared
prefix; everything after it (tool_name checks, threshold logic, etc.) is still
each hook's own.

`task_tracker_session.py` is the one hook whose `finish()` takes an extra
`additional_context` argument (for `UserPromptExpansion`'s
`hookSpecificOutput.additionalContext`, not the plain JSON `output` dict
every other hook prints) -- it does not fit the generic
`finish(code, output=None, **extra)` shape and is intentionally NOT handled
by `init_hook_context()`. That hook instead composes the smaller pieces
below (`configure_utf8_stdio()`, `read_json_stdin()`) directly with its own
`finish()`.
"""

import json
import os
import sys

from .hook_log import is_log_enabled, write_log


def configure_utf8_stdio():
    """Force UTF-8 stdio.

    Windows can default stdio to a locale codepage (e.g. cp932) instead of
    UTF-8; without this, JSON parsing and non-ASCII (e.g. Japanese) messages
    can break.
    """
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def read_json_stdin(finish):
    """Read+parse a JSON payload from stdin.

    On unparsable input, calls `finish(0, reason="unparsable stdin")` --
    which is expected to exit the process (as the `finish()` closures in
    this module and every hook script do) -- so this function only returns
    on success.
    """
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        finish(0, reason="unparsable stdin")


def make_finish(script_name, log, log_enabled):
    """Build the standard `finish(code, output=None, **extra)` closure.

    `extra` is merged into `log` before it's (optionally) written via
    `write_log()`. If `output` is given, it's printed to stdout as JSON
    (Claude Code hook output, e.g. `hookSpecificOutput`/`systemMessage`
    payloads) before the process exits with `code`.
    """

    def finish(code, output=None, **extra):
        log.update(extra)
        log["exit_code"] = code
        if log_enabled:
            write_log(script_name, log)
        if output is not None:
            print(json.dumps(output, ensure_ascii=False))
        sys.exit(code)

    return finish


def init_hook_context(script_name, enable_hook_log_default):
    """Run the full common hook-startup sequence and return its results.

    Combines `configure_utf8_stdio()`, debug-log-enabled resolution, `log`
    dict creation, `make_finish()`, and `read_json_stdin()` -- the sequence
    shared by the majority of hook scripts (see `block_large_read.py`'s
    `main()` for the minimal example this is based on). Returns
    `(payload, log, finish)`; `payload` is the parsed JSON stdin dict (this
    call never returns if stdin was unparsable, since `finish()` exits first).
    """
    configure_utf8_stdio()
    log_enabled = is_log_enabled(enable_hook_log_default)
    log = {}
    finish = make_finish(script_name, log, log_enabled)
    payload = read_json_stdin(finish)
    return payload, log, finish


def env_int(name, default):
    """Read an int-valued environment variable, falling back to `default`
    on missing/unparsable values."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
