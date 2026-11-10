"""Minimal single-key `.env` (KEY=VALUE) reader shared by hook scripts.

Stdlib-only, no python-dotenv dependency, and deliberately not a full
parser -- it only answers "what's the value of this one key in this one
file", which is all `hook_log.resolve_bool_flag()` and
`inject_env_vars.py`'s `@ref` resolution need.

Duplicate keys resolve **last-one-wins** (the last matching `KEY=...` line in
the file takes precedence over earlier ones), matching how real YAML/env
tooling resolves duplicate keys and `inject_env_vars.py`'s own
`parse_env_yaml()`.
"""


def strip_quotes(value):
    """Strip surrounding whitespace and one matching pair of `"`/`'` quotes."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def load_dotenv_value(path, key):
    """Read `key`'s value from the KEY=VALUE file at `path`.

    Returns `None` if the file doesn't exist/can't be read, or if `key` is
    never assigned in it. Blank lines, `#`-comments, and lines without `=`
    are skipped. Surrounding whitespace and a single matching pair of `"`/`'`
    quotes around the value are stripped, same as shell-style `.env` files.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None

    found = None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() != key:
            continue
        found = strip_quotes(value)
    return found
