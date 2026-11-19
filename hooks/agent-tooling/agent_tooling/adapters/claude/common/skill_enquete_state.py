"""Shared session-state helpers for the skill-usage-enquete hook pair.

`skill_usage_tracker.py` (PostToolUse) writes to this state; the paired
`skill_enquete_stop.py` (Stop) reads it. Kept in its own module (rather than
duplicated in both scripts) so the on-disk schema only has one definition.

State lives at `state/skill_usage/<session_id>.json` next to the installed
hooks (see `paths.hook_dir()`) -- one
file per session, holding the set of auto-enquete-enabled skills used so far
this session (name -> its skill directory) plus a `stop_attempts` counter the
Stop hook uses to cap how many turns it will keep asking about pending
surveys before giving up.

Must never raise on read: a missing/corrupt state file is treated the same
as "nothing tracked yet" so a bad file can never break the tool call or the
Stop hook it's attached to.
"""

import json
from pathlib import Path

ENQUETE_STATE_SUBDIR = ("state", "skill_usage")


def state_path(hooks_dir, session_id):
    return Path(hooks_dir).joinpath(*ENQUETE_STATE_SUBDIR, f"{session_id}.json")


def load_state(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"skills": {}, "stop_attempts": 0}
    if not isinstance(data, dict):
        return {"skills": {}, "stop_attempts": 0}
    skills = data.get("skills")
    if not isinstance(skills, dict):
        skills = {}
    stop_attempts = data.get("stop_attempts")
    if not isinstance(stop_attempts, int):
        stop_attempts = 0
    return {"skills": skills, "stop_attempts": stop_attempts}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
