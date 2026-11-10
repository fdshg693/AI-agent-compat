"""Session cache of directories already considered for AGENTS.md injection."""

import json
import hashlib
import os
import re
import tempfile


def cache_path_for(session_id, cache_name):
    raw = str(session_id or "unknown")
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._") or "unknown"
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
    return os.path.join(tempfile.gettempdir(), cache_name, f"{label[:80]}-{digest}.json")


def load_cache(session_id, cache_name):
    cache_path = cache_path_for(session_id, cache_name)
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return cache_path, set(json.load(f))
    except Exception:
        return cache_path, set()


def save_cache(cache_path, seen):
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(sorted(seen), f)
    except Exception:
        pass
