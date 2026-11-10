"""Unit tests for the tool-independent session registry (Step 2)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_tooling.core import sessions
from agent_tooling.hooks.scenarios.agent_sessions import registry
from agent_tooling.hooks.scenarios.agent_sessions.definition import (
    ENTRY_FIELDS,
    SCENARIO_ID,
)

UTC = timezone.utc
BASE = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
DEAD_PID = 2**31 - 1


@pytest.fixture
def reg(tmp_path, monkeypatch):
    directory = tmp_path / "registry"
    monkeypatch.setenv(sessions.DIRECTORY_ENV, str(directory))
    return directory


def json_files(directory: Path):
    return sorted(path.name for path in Path(directory).glob("*.json"))


def test_scenario_id_is_stable():
    assert SCENARIO_ID == "agent_sessions"


def test_start_creates_entry_with_expected_fields(reg):
    path = sessions.start_session(
        "claude",
        "session-1",
        cwd="/work/a",
        pid=os.getpid(),
        pid_source="agent",
        hook_event="SessionStart",
        now=BASE,
    )
    assert path is not None
    assert Path(path).is_file()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert set(data) == set(ENTRY_FIELDS)
    assert data["agent"] == "claude"
    assert data["session_id"] == "session-1"
    assert data["pid"] == os.getpid()
    assert data["pid_source"] == "agent"
    assert data["cwd"] == "/work/a"
    assert data["started_at"] == data["last_seen"] == BASE.isoformat()
    assert data["schema"] == sessions.SCHEMA_VERSION
    assert data["hook_event"] == "SessionStart"


def test_cwd_updates_and_end_deletes(reg):
    sessions.start_session("claude", "s", cwd="/work/a", pid=0, pid_source="unknown")
    sessions.update_session("claude", "s", cwd="/work/b", hook_event="CwdChanged")
    entries = sessions.list_entries()
    assert [entry["cwd"] for entry in entries] == ["/work/b"]
    assert entries[0]["hook_event"] == "CwdChanged"

    assert sessions.end_session("claude", "s") is True
    assert sessions.list_entries() == []
    assert sessions.end_session("claude", "s") is False


def test_update_without_start_does_not_create(reg):
    assert sessions.update_session("claude", "ghost", cwd="/x") is None
    assert sessions.update_session("claude", "ghost", hook_event="heartbeat") is None
    assert json_files(reg) == []


def test_cwd_after_end_does_not_resurrect(reg):
    sessions.start_session("claude", "s", cwd="/work/a")
    sessions.end_session("claude", "s")
    sessions.update_session("claude", "s", cwd="/work/b")
    assert json_files(reg) == []


def test_start_overwrites_same_file(reg):
    sessions.start_session("claude", "s", cwd="/a", now=BASE)
    sessions.start_session("claude", "s", cwd="/b", now=BASE + timedelta(seconds=5))
    assert json_files(reg) == [sessions.session_file_name("claude", "s")]
    entry = sessions.list_entries()[0]
    assert entry["cwd"] == "/b"
    assert entry["started_at"] == (BASE + timedelta(seconds=5)).isoformat()


def test_file_name_is_deterministic_and_agent_scoped():
    name = sessions.session_file_name("claude", "abc")
    assert name == sessions.session_file_name("claude", "abc")
    assert name.endswith(".json")
    assert name.startswith("claude-")
    assert sessions.session_file_name("codex", "abc") != name


def test_blank_or_missing_session_id_is_ignored(reg):
    assert sessions.start_session("claude", "", cwd="/a") is None
    assert sessions.start_session("claude", "   ", cwd="/a") is None
    assert sessions.start_session("claude", None, cwd="/a") is None
    assert sessions.start_session("", "s", cwd="/a") is None
    assert json_files(reg) == []


def test_live_when_real_pid_is_alive(reg):
    sessions.start_session("claude", "live", cwd="/a", pid=os.getpid(), pid_source="agent")
    entry = sessions.list_entries()[0]
    assert sessions.is_pid_alive(os.getpid()) is True
    assert sessions.is_live(entry) is True
    assert sessions.entry_state(entry) == "live"


def test_dead_pid_is_stale(reg):
    sessions.start_session("claude", "dead", cwd="/a", pid=DEAD_PID, pid_source="agent")
    entry = sessions.list_entries()[0]
    assert sessions.is_pid_alive(DEAD_PID) is False
    assert sessions.is_live(entry, now=BASE) is False
    assert sessions.entry_state(entry, now=BASE) == "stale"


def test_unknown_pid_source_uses_ttl(reg):
    sessions.start_session("kilo", "unknown", cwd="/a", pid=0, pid_source="unknown", now=BASE)
    entry = sessions.list_entries()[0]
    assert sessions.is_live(entry, now=BASE + timedelta(seconds=50), ttl=100) is True
    assert sessions.is_live(entry, now=BASE + timedelta(seconds=200), ttl=100) is False
    assert sessions.is_live(entry, now=BASE + timedelta(seconds=200), ttl=10_000) is True


def test_default_ttl_env_override(monkeypatch):
    monkeypatch.delenv(sessions.TTL_ENV, raising=False)
    assert sessions.default_ttl() == sessions.DEFAULT_TTL_SECONDS
    monkeypatch.setenv(sessions.TTL_ENV, "1.5")
    assert sessions.default_ttl() == 1.5
    monkeypatch.setenv(sessions.TTL_ENV, "not-a-number")
    assert sessions.default_ttl() == sessions.DEFAULT_TTL_SECONDS


def test_prune_removes_stale_and_corrupt_but_keeps_live(reg):
    sessions.start_session("claude", "live", cwd="/a", pid=os.getpid(), pid_source="agent")
    sessions.start_session("claude", "dead", cwd="/a", pid=DEAD_PID, pid_source="agent", now=BASE)
    (reg / "broken.json").write_text("{not json", encoding="utf-8")

    removed = sessions.prune()
    assert removed == 2
    assert json_files(reg) == [sessions.session_file_name("claude", "live")]


def test_pid_can_be_shared_across_sessions(reg):
    sessions.start_session("kilo", "one", cwd="/a", pid=os.getpid(), pid_source="host")
    sessions.start_session("kilo", "two", cwd="/b", pid=os.getpid(), pid_source="host")
    assert len(json_files(reg)) == 2
    assert all(sessions.is_live(entry) for entry in sessions.list_entries())


def test_corrupt_and_invalid_entries_are_skipped(reg):
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "broken.json").write_text("{not json", encoding="utf-8")
    (reg / "array.json").write_text("[]", encoding="utf-8")
    (reg / "empty.json").write_text(
        json.dumps({"agent": "claude", "session_id": "   "}), encoding="utf-8"
    )
    sessions.start_session("claude", "good", cwd="/a")
    assert len(sessions.list_entries()) == 1


def test_list_entries_sorted_by_agent_cwd_started(reg):
    sessions.start_session("codex", "c", cwd="/z", now=BASE + timedelta(seconds=2))
    sessions.start_session("codex", "c2", cwd="/a", now=BASE + timedelta(seconds=3))
    sessions.start_session("claude", "a", cwd="/z", now=BASE + timedelta(seconds=1))
    order = [(entry["agent"], entry["cwd"]) for entry in sessions.list_entries()]
    assert order == [("claude", "/z"), ("codex", "/a"), ("codex", "/z")]


def test_registry_apply_event_lifecycle(reg):
    assert registry.apply_event(
        "claude", "start", "s1", cwd="/work", pid=os.getpid(), pid_source="agent"
    )
    assert registry.apply_event("claude", "cwd", "s1", cwd="/work/sub")
    assert sessions.list_entries()[0]["cwd"] == "/work/sub"
    assert registry.apply_event("claude", "heartbeat", "s1")
    assert registry.apply_event("claude", "end", "s1")
    assert sessions.list_entries() == []


def test_registry_apply_event_is_fail_open(reg):
    assert registry.apply_event("claude", "nope", "s1", cwd="/x") is False
    assert registry.apply_event("", "start", "s1", cwd="/x") is False
    assert registry.apply_event("claude", "cwd", "s1") is False
    assert registry.apply_event("claude", "end", None) is False
    assert registry.apply_event(None, "start", "s1", cwd="/x") is False


def test_list_entries_on_missing_directory_returns_empty(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert sessions.list_entries(str(missing)) == []
    assert sessions.prune(str(missing)) == 0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits only")
def test_directory_and_file_permissions(reg):
    path = sessions.start_session("claude", "perm", cwd="/a")
    assert path is not None
    assert oct(os.stat(reg).st_mode & 0o777) == "0o700"
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


def test_symlinked_registry_dir_is_rejected(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    monkeypatch.setenv(sessions.DIRECTORY_ENV, str(link))
    assert sessions.start_session("claude", "s", cwd="/a") is None
    assert json_files(real) == []


def test_find_agent_pid_skips_shells(monkeypatch):
    tree = {
        100: (90, "pwsh"),
        90: (80, "node"),
        80: (0, "init"),
    }
    monkeypatch.setattr(sessions, "_process_name", lambda pid: (tree.get(int(pid)) or (0, None))[1])
    monkeypatch.setattr(
        sessions, "_parent_pid", lambda pid: (tree.get(int(pid)) or (None, None))[0]
    )
    assert sessions.find_agent_pid(100) == (90, "agent")


def test_find_agent_pid_unknown_when_name_missing(monkeypatch):
    monkeypatch.setattr(sessions, "_process_name", lambda pid: None)
    assert sessions.find_agent_pid(123) == (0, "unknown")


def test_find_agent_pid_gives_up_on_all_shells(monkeypatch):
    monkeypatch.setattr(sessions, "_process_name", lambda pid: "bash")
    monkeypatch.setattr(sessions, "_parent_pid", lambda pid: int(pid) + 1)
    assert sessions.find_agent_pid(1, max_depth=3) == (0, "unknown")


def test_is_shell_name_ignores_case_and_extension():
    assert sessions.is_shell_name("PowerShell.EXE") is True
    assert sessions.is_shell_name("py.exe") is True
    assert sessions.is_shell_name("node") is False
    assert sessions.is_shell_name("claude") is False


def test_normalize_entry_rejects_non_dict():
    assert sessions.normalize_entry(None) is None
    assert sessions.normalize_entry("x") is None
    assert sessions.normalize_entry({"agent": "claude"}) is None


def test_registry_dir_prefers_argument_over_env(reg, tmp_path):
    other = tmp_path / "explicit"
    assert sessions.registry_dir(str(other)) == os.path.abspath(str(other))
    assert sessions.registry_dir() == os.path.abspath(str(reg))


def test_atomic_write_leaves_no_partial_files(reg):
    sessions.start_session("claude", "s", cwd="/a")
    leftovers = [name for name in os.listdir(reg) if name.startswith(".tmp-")]
    assert leftovers == []
