"""Shared SKILL.md frontmatter helpers for the skill-usage-enquete hook pair.

Used by `skill_usage_tracker.py` to read a skill's YAML frontmatter (to
check `auto-enquete: true`) and, for Skill-tool invocations (which only give
a skill name, not a path), to resolve that name back to a skill directory by
scanning a list of search roots for `SKILL.md` files.

Must never raise: a missing/malformed SKILL.md is just treated as "no
frontmatter" so a single bad skill file can't break tracking for any other
skill.
"""

import yaml

from agent_tooling.core.fs_links import find_files


def read_frontmatter(skill_md_path):
    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def find_skill_dir_by_name(name, roots):
    """Search `roots` (iterable of Path) recursively for a SKILL.md whose
    frontmatter `name` matches `name` (case-insensitive).

    Falls back to a directory whose basename matches, if no frontmatter-name
    match is found anywhere across the roots. Scans all roots fully before
    falling back, so a real name match anywhere always wins over a
    directory-name coincidence.
    """
    name_lower = name.strip().lower()
    fallback = None
    for root in roots:
        if not root.is_dir():
            continue
        for skill_md in sorted(find_files(root, "SKILL.md")):
            frontmatter = read_frontmatter(skill_md)
            if frontmatter is None:
                continue
            fm_name = frontmatter.get("name")
            if isinstance(fm_name, str) and fm_name.strip().lower() == name_lower:
                return skill_md.parent
            if fallback is None and skill_md.parent.name.lower() == name_lower:
                fallback = skill_md.parent
    return fallback
