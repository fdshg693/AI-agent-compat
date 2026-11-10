"""Tests for the agent-sessions CLI (live/stale, --all/--prune/--json/--agent)."""

from __future__ import annotations

import io
import itertools
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_tooling import sessions_cli
from agent_tooling.core import sessions
from agent_tooling.sessions_cli import COLUMNS, build_parser, main, run_watch

DEAD_PID = 2**31 - 1
UTC = timezone.utc
BASE = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
_LIVE_PIDS = itertools.count(100_000)


@pytest.fixture
def reg(tmp_path, monkeypatch):
    directory = tmp_path / "reg"
    monkeypatch.setenv(sessions.DIRECTORY_ENV, str(directory))
    return directory


@pytest.fixture(autouse=True)
def _fake_liveness(monkeypatch):
    """Distinct live entries use synthetic PIDs; only ``DEAD_PID`` is dead."""
    monkeypatch.setattr(sessions, "is_pid_alive", lambda pid: int(pid) != DEAD_PID)


def add_live(agent="claude", session_id="live", cwd="/a", when=None):
    sessions.start_session(
        agent,
        session_id,
        cwd=cwd,
        pid=next(_LIVE_PIDS),
        pid_source="agent",
        now=when or BASE,
    )


def add_stale(agent="codex", session_id="stale", cwd="/b", when=None):
    sessions.start_session(
        agent,
        session_id,
        cwd=cwd,
        pid=DEAD_PID,
        pid_source="agent",
        now=when or BASE,
    )


def test_empty_registry_exits_zero(reg, capsys):
    assert main([]) == 0
    assert "(no active sessions)" in capsys.readouterr().out


def test_default_shows_only_live(reg, capsys):
    add_live(agent="claude")
    add_stale(agent="codex")
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "claude" in out
    assert "codex" not in out
    assert "stale" not in out
    assert "live" in out


def test_all_includes_stale(reg, capsys):
    add_live(agent="claude")
    add_stale(agent="codex")
    assert main(["--all"]) == 0
    out = capsys.readouterr().out
    assert "claude" in out
    assert "codex" in out
    assert "stale" in out
    assert "live" in out


def test_prune_removes_stale_but_not_live(reg, capsys):
    add_live(agent="claude", session_id="keep")
    add_stale(agent="codex", session_id="drop")
    assert main(["--prune"]) == 0
    captured = capsys.readouterr()
    assert "pruned 1 stale session(s)" in captured.err
    remaining = [path.name for path in Path(reg).glob("*.json")]
    assert remaining == [sessions.session_file_name("claude", "keep")]


def test_prune_then_all_shows_no_stale(reg, capsys):
    add_live(agent="claude")
    add_stale(agent="codex")
    main(["--prune", "--all"])
    out = capsys.readouterr().out
    assert "codex" not in out


def test_json_default_is_list(reg, capsys):
    add_live(agent="claude")
    add_stale(agent="codex")
    assert main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert set(payload[0]) == {
        "agent",
        "session_id",
        "pid",
        "pid_source",
        "cwd",
        "started_at",
        "last_seen",
        "state",
    }
    assert payload[0]["agent"] == "claude"
    assert payload[0]["state"] == "live"


def test_json_all_includes_stale(reg, capsys):
    add_live(agent="claude")
    add_stale(agent="codex")
    assert main(["--json", "--all"]) == 0
    payload = json.loads(capsys.readouterr().out)
    states = {item["agent"]: item["state"] for item in payload}
    assert states == {"claude": "live", "codex": "stale"}


def test_json_with_prune_wraps_result(reg, capsys):
    add_live(agent="claude", session_id="keep")
    add_stale(agent="codex", session_id="drop")
    assert main(["--json", "--prune"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["pruned"] == 1
    assert [item["session_id"] for item in payload["sessions"]] == ["keep"]
    assert "pruned 1" in captured.err


def test_agent_filter(reg, capsys):
    add_live(agent="claude", session_id="c")
    add_live(agent="codex", session_id="x")
    assert main(["--json", "--agent", "codex"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["agent"] for item in payload] == ["codex"]


def test_unknown_agent_filter_is_empty(reg, capsys):
    add_live(agent="claude")
    assert main(["--agent", "nope"]) == 0
    assert "(no active sessions)" in capsys.readouterr().out


def test_corrupt_entry_is_skipped_with_warning(reg, capsys):
    add_live(agent="claude")
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "broken.json").write_text("{not json", encoding="utf-8")
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "unreadable entry" in captured.err
    assert "claude" in captured.out


def test_main_collapses_duplicate_pid_entries(reg, capsys):
    sessions.start_session("claude", "old", cwd="/a", pid=777_001, pid_source="agent", now=BASE)
    sessions.start_session(
        "claude",
        "new",
        cwd="/b",
        pid=777_001,
        pid_source="agent",
        now=BASE + timedelta(seconds=5),
    )
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "removed 1 duplicate-PID session(s)" in captured.err
    assert "new" in captured.out
    assert "old" not in captured.out
    remaining = [path.name for path in Path(reg).glob("*.json")]
    assert remaining == [sessions.session_file_name("claude", "new")]


def test_main_collapses_shared_host_pids(reg, capsys):
    sessions.start_session("kilo", "old", cwd="/a", pid=777_002, pid_source="host", now=BASE)
    sessions.start_session(
        "kilo", "new", cwd="/b", pid=777_002, pid_source="host", now=BASE + timedelta(seconds=5)
    )
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "removed 1 duplicate-PID session(s)" in captured.err
    remaining = [path.name for path in Path(reg).glob("*.json")]
    assert remaining == [sessions.session_file_name("kilo", "new")]


def test_main_keeps_distinct_pids(reg):
    sessions.start_session("kilo", "one", cwd="/a", pid=777_003, pid_source="host")
    sessions.start_session("kilo", "two", cwd="/b", pid=777_004, pid_source="host")
    assert main([]) == 0
    assert len([path for path in Path(reg).glob("*.json")]) == 2


def watch_args(*extra):
    return build_parser().parse_args(["--watch", *extra])


def test_watch_interval_must_be_positive(reg):
    for value in ("0", "-1", "nope"):
        with pytest.raises(SystemExit):
            main(["--watch", "--interval", value])


def test_watch_json_emits_one_record_per_frame(reg):
    add_live(agent="claude")
    out = io.StringIO()
    code = run_watch(
        watch_args("--json"),
        interval=1,
        output=out,
        sleep=lambda _seconds: None,
        max_frames=2,
        tty=False,
    )
    assert code == 0
    lines = out.getvalue().strip().splitlines()
    assert len(lines) == 2
    assert [json.loads(line)[0]["agent"] for line in lines] == ["claude", "claude"]


def test_watch_tty_redraws_in_place(reg):
    add_live(agent="claude")
    out = io.StringIO()
    run_watch(
        watch_args(),
        interval=1,
        output=out,
        sleep=lambda _seconds: None,
        max_frames=2,
        tty=True,
    )
    text = out.getvalue()
    assert text.count("\x1b[H\x1b[J") == 2
    assert text.startswith("\x1b[?25l")
    assert text.endswith("\x1b[?25h")


def test_watch_non_tty_appends_frames_without_ansi(reg):
    add_live(agent="claude")
    out = io.StringIO()
    run_watch(
        watch_args(),
        interval=1,
        output=out,
        sleep=lambda _seconds: None,
        max_frames=2,
        tty=False,
    )
    text = out.getvalue()
    assert "\x1b" not in text
    assert text.count("AGENT") == 2


def test_watch_prune_count_is_in_frame_not_stderr(reg, capsys):
    add_live(agent="claude", session_id="keep")
    add_stale(agent="codex", session_id="drop")
    out = io.StringIO()
    run_watch(
        watch_args("--prune"),
        interval=1,
        output=out,
        sleep=lambda _seconds: None,
        max_frames=1,
        tty=False,
    )
    assert "(pruned 1 stale session(s))" in out.getvalue()
    assert capsys.readouterr().err == ""


def test_watch_json_with_prune_wraps_ndjson(reg):
    add_live(agent="claude")
    add_stale(agent="codex")
    out = io.StringIO()
    run_watch(
        watch_args("--json", "--prune"),
        interval=1,
        output=out,
        sleep=lambda _seconds: None,
        max_frames=1,
        tty=False,
    )
    payload = json.loads(out.getvalue().strip())
    assert payload["pruned"] == 1
    assert [item["agent"] for item in payload["sessions"]] == ["claude"]


def test_watch_keyboard_interrupt_restores_cursor(reg):
    add_live(agent="claude")
    out = io.StringIO()

    def interrupt(_seconds):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_watch(
            watch_args(),
            interval=1,
            output=out,
            sleep=interrupt,
            max_frames=5,
            tty=True,
        )
    assert out.getvalue().endswith("\x1b[?25h")


def test_watch_stops_when_downstream_pipe_closes(reg):
    add_live(agent="claude")

    class ClosedPipe(io.StringIO):
        def write(self, _text):
            raise BrokenPipeError

    waits = []
    code = run_watch(
        watch_args(),
        interval=1,
        output=ClosedPipe(),
        sleep=waits.append,
        max_frames=5,
        tty=False,
    )
    assert code == 0
    assert waits == []


def test_main_watch_returns_zero_on_interrupt(reg, monkeypatch):
    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(sessions_cli, "run_watch", interrupt)
    assert main(["--watch"]) == 0


def test_text_is_sorted_and_has_headers(reg, capsys):
    add_live(agent="codex", session_id="c2", cwd="/a", when=BASE + timedelta(seconds=3))
    add_live(agent="codex", session_id="c1", cwd="/z", when=BASE + timedelta(seconds=1))
    add_live(agent="claude", session_id="c0", cwd="/z", when=BASE + timedelta(seconds=2))
    assert main([]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith(COLUMNS[0])
    assert COLUMNS[-1] in lines[0]
    assert lines[1].startswith("claude")
    assert " c0 " in lines[1]
    assert lines[2].startswith("codex")
    assert " c2 " in lines[2]
    assert " c1 " in lines[3]
