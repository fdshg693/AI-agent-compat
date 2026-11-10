"""Best-effort path extraction from Bash / PowerShell read commands."""

import os
import re

from .paths import split_subcommands, tokenize

# Best-effort table of common file-reading commands (Git Bash / POSIX and
# PowerShell/cmd, since this repo runs on Windows with both shells
# available). `flag_values`: flags that consume the next token as their
# value (so it must not be treated as a path). `skip_first_positional`:
# the command's first non-flag argument is a pattern/script, not a path
# (grep/rg/findstr/Select-String's search pattern, sed's script when no
# -e/-f was given).
BASH_READ_COMMAND_SPECS = {
    "cat": {"flag_values": set()},
    "less": {"flag_values": set()},
    "more": {"flag_values": set()},
    "type": {"flag_values": set()},
    "head": {"flag_values": {"-n", "-c"}},
    "tail": {"flag_values": {"-n", "-c"}},
    "sed": {
        "flag_values": {"-e", "-f", "-i"},
        "skip_first_positional": True,
        "unless_flags": {"-e", "-f"},
    },
    "get-content": {
        "flag_values": {"-totalcount", "-tail", "-readcount", "-delimiter", "-encoding", "-stream"},
    },
    "gc": {
        "flag_values": {"-totalcount", "-tail", "-readcount", "-delimiter", "-encoding", "-stream"},
    },
    "grep": {
        "flag_values": {"-e", "-f", "-m", "-a", "-b", "-c", "-g", "-t"},
        "skip_first_positional": True,
    },
    "rg": {
        "flag_values": {
            "-e",
            "-f",
            "-m",
            "-a",
            "-b",
            "-c",
            "-g",
            "-t",
            "--type",
            "--glob",
            "--context",
        },
        "skip_first_positional": True,
    },
    "findstr": {"flag_values": set(), "skip_first_positional": True},
    "select-string": {
        "flag_values": {"-pattern", "-context", "-encoding"},
        "skip_first_positional": True,
    },
}
CD_COMMANDS = {"cd", "chdir", "pushd", "set-location", "sl"}


def extract_bash_dirs(command, cwd):
    """Best-effort: guess which files/dirs a shell command reads, by
    recognizing common read commands (cat/head/tail/sed/rg/grep/... and
    their PowerShell equivalents). Only paths that actually exist on disk
    are kept, which filters out most mis-parsed patterns/flags.

    Tracks a virtual cwd across `cd`/`Set-Location` in a chained command
    (e.g. `cd tools/foo && cat AGENTS.md`) so later subcommands in the
    same chain resolve relative paths correctly."""
    dirs = set()
    virtual_cwd = cwd
    for subcmd in split_subcommands(command):
        tokens = tokenize(subcmd)
        if not tokens:
            continue
        name = re.sub(r"\.(exe|ps1)$", "", os.path.basename(tokens[0]).lower())

        if name in CD_COMMANDS:
            target = next((t for t in tokens[1:] if not t.startswith("-")), None)
            if target:
                virtual_cwd = os.path.normpath(
                    target if os.path.isabs(target) else os.path.join(virtual_cwd, target)
                )
            continue

        spec = BASH_READ_COMMAND_SPECS.get(name)
        if spec is None:
            continue

        flag_values = spec.get("flag_values", set())
        flags_present = {t.lower() for t in tokens[1:] if t.startswith("-")}
        skip_first = spec.get("skip_first_positional", False)
        unless_flags = spec.get("unless_flags")
        if unless_flags and flags_present & unless_flags:
            skip_first = False

        positionals = []
        i = 1
        while i < len(tokens):
            t = tokens[i]
            if t.startswith("-"):
                i += 2 if t.lower() in flag_values else 1
                continue
            positionals.append(t)
            i += 1
        if skip_first and positionals:
            positionals = positionals[1:]

        for p in positionals:
            if not p or p in ("-", ".", ".."):
                continue
            abs_path = os.path.normpath(p if os.path.isabs(p) else os.path.join(virtual_cwd, p))
            if os.path.isdir(abs_path):
                dirs.add(abs_path)
            elif os.path.isfile(abs_path):
                dirs.add(os.path.dirname(abs_path))
    return dirs


def extract_bash_paths(command, cwd):
    """Return existing files read by a recognizable shell command.

    Unlike ``extract_bash_dirs``, this deliberately excludes directories and
    keeps the concrete file path for scoped Rule matching.
    """
    paths = set()
    virtual_cwd = cwd
    for subcmd in split_subcommands(command):
        tokens = tokenize(subcmd)
        if not tokens:
            continue
        name = re.sub(r"\.(exe|ps1)$", "", os.path.basename(tokens[0]).lower())
        if name in CD_COMMANDS:
            target = next((t for t in tokens[1:] if not t.startswith("-")), None)
            if target:
                virtual_cwd = os.path.normpath(
                    target if os.path.isabs(target) else os.path.join(virtual_cwd, target)
                )
            continue
        spec = BASH_READ_COMMAND_SPECS.get(name)
        if spec is None:
            continue
        flag_values = spec.get("flag_values", set())
        flags_present = {t.lower() for t in tokens[1:] if t.startswith("-")}
        skip_first = spec.get("skip_first_positional", False)
        unless_flags = spec.get("unless_flags")
        if unless_flags and flags_present & unless_flags:
            skip_first = False
        positionals = []
        i = 1
        while i < len(tokens):
            token = tokens[i]
            if token.startswith("-"):
                i += 2 if token.lower() in flag_values else 1
                continue
            positionals.append(token)
            i += 1
        if skip_first and positionals:
            positionals = positionals[1:]
        for value in positionals:
            if not value or value in ("-", ".", ".."):
                continue
            path = os.path.normpath(
                value if os.path.isabs(value) else os.path.join(virtual_cwd, value)
            )
            if os.path.isfile(path):
                paths.add(path)
    return paths
