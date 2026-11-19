"""通知の抑止状態（`agent_tooling/notify/state.py`）のテスト。OS に依存しない。"""

from __future__ import annotations

import json
import time

import pytest

from agent_tooling.notify import state

NOW = 1_700_000_000.0


def _read(tmp_path) -> dict:
    return json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))


def test_missing_file_means_no_suppression(tmp_path):
    assert state._state_check(tmp_path, "sid", NOW) == {"snooze": None, "mute": None}
    assert state._state_check(None, "sid", NOW) == {"snooze": None, "mute": None}


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[]",
        '{"version": 2, "global": {"snooze_until": 9999999999}}',
        '{"version": 1, "global": {"snooze_until": "9999999999"}, "sessions": []}',
        '{"version": 1, "global": {"snooze_until": true}}',
    ],
)
def test_broken_file_means_no_suppression(tmp_path, content):
    (tmp_path / "state.json").write_text(content, encoding="utf-8")
    assert state._state_check(tmp_path, "sid", NOW) == {"snooze": None, "mute": None}


def test_global_snooze_applies_to_every_session(tmp_path):
    state._state_set(tmp_path, "snooze", "global", NOW + 900, now=NOW)
    for sid in ("a", "b", ""):
        assert state._state_check(tmp_path, sid, NOW) == {
            "snooze": {"scope": "global", "until": NOW + 900},
            "mute": None,
        }


def test_session_mute_applies_only_to_that_session(tmp_path):
    state._state_set(tmp_path, "mute", "session", NOW + 60, session_id="a", now=NOW)
    assert state._state_check(tmp_path, "a", NOW)["mute"] == {"scope": "session", "until": NOW + 60}
    assert state._state_check(tmp_path, "b", NOW)["mute"] is None
    assert state._state_check(tmp_path, "", NOW)["mute"] is None


def test_later_deadline_wins_between_scopes(tmp_path):
    state._state_set(tmp_path, "mute", "global", NOW + 100, now=NOW)
    state._state_set(tmp_path, "mute", "session", NOW + 500, session_id="a", now=NOW)
    assert state._state_check(tmp_path, "a", NOW)["mute"] == {
        "scope": "session",
        "until": NOW + 500,
    }
    assert state._state_check(tmp_path, "b", NOW)["mute"] == {"scope": "global", "until": NOW + 100}


def test_expired_values_are_ignored_and_pruned_on_write(tmp_path):
    state._state_set(tmp_path, "snooze", "global", NOW + 10, now=NOW)
    state._state_set(tmp_path, "mute", "session", NOW + 10, session_id="old", now=NOW)
    later = NOW + 20
    assert state._state_check(tmp_path, "old", later) == {"snooze": None, "mute": None}

    state._state_set(tmp_path, "mute", "session", later + 60, session_id="new", now=later)
    assert _read(tmp_path) == {
        "version": 1,
        "global": {},
        "sessions": {"new": {"mute_until": later + 60}},
    }


def test_session_deadline_is_capped(tmp_path):
    state._state_set(tmp_path, "mute", "session", NOW + 10**9, session_id="a", now=NOW)
    until = state._state_check(tmp_path, "a", NOW)["mute"]["until"]
    assert until == NOW + state._STATE_SESSION_MAX_SECONDS


def test_set_replaces_same_kind_and_scope(tmp_path):
    state._state_set(tmp_path, "snooze", "global", NOW + 3600, now=NOW)
    state._state_set(tmp_path, "snooze", "global", NOW + 900, now=NOW)
    assert state._state_check(tmp_path, "", NOW)["snooze"]["until"] == NOW + 900


@pytest.mark.parametrize(
    "kind, scope, session_id",
    [("loud", "global", ""), ("mute", "project", ""), ("mute", "session", "")],
)
def test_set_rejects_bad_arguments(tmp_path, kind, scope, session_id):
    with pytest.raises(ValueError):
        state._state_set(tmp_path, kind, scope, NOW + 1, session_id=session_id, now=NOW)


def test_clear_removes_global_and_own_session_only(tmp_path):
    state._state_set(tmp_path, "snooze", "global", NOW + 100, now=NOW)
    state._state_set(tmp_path, "mute", "global", NOW + 100, now=NOW)
    state._state_set(tmp_path, "mute", "session", NOW + 100, session_id="a", now=NOW)
    state._state_set(tmp_path, "mute", "session", NOW + 100, session_id="b", now=NOW)

    state._state_clear(tmp_path, session_id="a", now=NOW)
    assert state._state_check(tmp_path, "a", NOW) == {"snooze": None, "mute": None}
    assert state._state_check(tmp_path, "b", NOW)["mute"] == {
        "scope": "session",
        "until": NOW + 100,
    }


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "nested" / "dir"
    state._state_set(target, "mute", "global", NOW + 1, now=NOW)
    assert (target / "state.json").is_file()
    assert list(target.glob("*.tmp")) == []


def test_write_overwrites_broken_file(tmp_path):
    (tmp_path / "state.json").write_text("garbage", encoding="utf-8")
    state._state_set(tmp_path, "mute", "global", NOW + 1, now=NOW)
    assert _read(tmp_path)["global"] == {"mute_until": NOW + 1}


def test_end_of_today_is_next_local_midnight():
    now = time.mktime((2026, 3, 31, 15, 30, 0, 0, 0, -1))
    end = state._state_end_of_today(now)
    tm = time.localtime(end)
    assert (tm.tm_year, tm.tm_mon, tm.tm_mday, tm.tm_hour, tm.tm_min) == (2026, 4, 1, 0, 0)
    assert 0 < end - now <= 24 * 3600
