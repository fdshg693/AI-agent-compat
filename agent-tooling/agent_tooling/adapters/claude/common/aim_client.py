"""Shared `aim` CLI (tools/aim, OpenRouter-backed) subprocess wrapper.

Consolidates the part of each hook's `call_aim()` that was byte-for-byte
identical across `summarize_read.py`, `summarize_webfetch.py`, and
`translate_prompt.py`: invoking `aim --model <model>` with the fully
assembled prompt on stdin, then converting a non-zero exit code or an empty
response into a `RuntimeError`.

Prompt assembly (truncation, system/user prompt formatting) is hook-specific
and stays in each hook script -- this module only takes the final prompt
string that should go to `aim` on stdin.

Timeouts (`subprocess.TimeoutExpired`) and OS-level failures (`OSError`,
e.g. `aim` not found on PATH) are NOT caught here; they propagate to the
caller -- each hook's `main()` catches
`(subprocess.TimeoutExpired, RuntimeError, OSError)` around its `call_aim()`
call and falls through silently.
"""

import os
import subprocess


def run_aim(model, prompt, timeout):
    """Run `aim --model <model>` with `prompt` on stdin and return its stdout.

    Raises `RuntimeError` if `aim` exits non-zero or returns an empty
    response. Raises `subprocess.TimeoutExpired` / `OSError` uncaught, same
    as a direct `subprocess.run()` call would.
    """
    proc = subprocess.run(
        ["aim", "--model", model],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"aim exited with code {proc.returncode}: {proc.stderr.strip()}")

    output = proc.stdout.strip()
    if not output:
        raise RuntimeError(f"aim returned empty output: {proc.stderr.strip()}")
    return output
