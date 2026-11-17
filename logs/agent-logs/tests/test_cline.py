import builtins
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from agent_logs import cli
from agent_logs.adapters.cline import ClineAdapter
from agent_logs.model import Filters
from agent_logs.query import find_session

A = "1780000000000_aaaaa"
B = "1780000100000_bbbbb"
SUB = "1780000200000_ccccc"
GONE = "1780000300000_ddddd"
MIGRATED = "1770000000000"  # same id in SDK sessions and legacy tasks
VIA_META = "1770000500000"  # legacy task referenced by metadata.migratedFromLegacyTask
LEGACY = "1770000900000"
OLD_CLI = "1760000000000"


def _sessions():
    a = ClineAdapter()
    return a, {s.id: s for s in a.iter_sessions(Filters())}


def _lines(out: str):
    return [json.loads(x) for x in out.splitlines() if x.strip()]


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_detect(fixture_home):
    fixture_home("cline")
    src = {s.source: s for s in ClineAdapter().detect()}
    assert src["sdk"].exists and src["sdk"].count == 4
    assert src["sdk-index"].exists and src["sdk-index"].count == 4
    assert src["vscode-legacy"].exists and src["vscode-legacy"].count == 3
    assert src["cli-legacy"].count == 1
    assert "cursor-legacy" not in src  # absent forks are not listed


def test_sessions_both_systems_and_dedup(fixture_home):
    fixture_home("cline")
    a, ss = _sessions()
    assert set(ss) == {A, B, SUB, GONE, MIGRATED, LEGACY, OLD_CLI}
    assert VIA_META not in ss
    assert ss[MIGRATED].source == "vscode"  # SDK copy wins
    assert ss[MIGRATED].title == "Migrated task (sdk copy)"

    s = ss[A]
    assert s.source == "cli" and s.project == "C:/Users/alice/proj"
    assert s.cwd == "C:\\Users\\alice\\proj\\sub"
    assert s.title == "Fix the build" and s.model == "example-model"
    assert s.started_at == _utc(2026, 5, 28, 20, 26, 40)
    assert s.ended_at == _utc(2026, 5, 28, 20, 30, 0)
    assert (s.message_count, s.tool_call_count) == (4, 1)
    # SDK inputTokens (30) includes cacheReadTokens (20); tokens_in excludes cache reads
    assert (s.tokens_in, s.tokens_out, s.tokens_cache_read, s.tokens_cache_write) == (10, 15, 20, 0)
    assert s.cost == 0.003

    b = ss[B]
    assert b.source == "vscode" and b.title == "Add tests" and b.ended_at is not None
    # metadata.usage smaller than the per-message metrics -> the metrics sum wins
    assert (b.tokens_in, b.tokens_out, b.tokens_cache_write) == (100, 50, 10)
    assert b.cost == 0.05
    assert (b.message_count, b.tool_call_count) == (1, 1)

    sub = ss[SUB]
    assert sub.source == "subagent" and sub.parent_id == A
    assert (sub.tokens_in, sub.tokens_out) == (7, 3)

    gone = ss[GONE]  # only in sessions.db
    assert gone.title == "Gone session" and gone.message_count is None
    assert (gone.tokens_in, gone.cost) == (5, 0.0005)

    leg = ss[LEGACY]
    assert leg.source == "vscode-legacy" and leg.project == "C:/Users/alice/legacy"
    assert leg.title == "Refactor utils" and leg.model == "legacy-model"
    assert leg.started_at == _utc(2026, 2, 2, 2, 55, 0)
    assert leg.ended_at == datetime.fromtimestamp(1770000999, timezone.utc)
    assert (leg.message_count, leg.tool_call_count) == (3, 1)
    # taskHistory totals; recorded zero cost stays 0.0 (not None)
    assert (leg.tokens_in, leg.tokens_out, leg.tokens_cache_read, leg.tokens_cache_write) == (
        300,
        40,
        100,
        0,
    )
    assert leg.cost == 0.0

    old = ss[OLD_CLI]  # no taskHistory -> sums of api_req_started
    assert old.source == "cli-legacy" and old.title == "Old cli task"
    assert (old.tokens_in, old.tokens_out, old.tokens_cache_read, old.tokens_cache_write) == (
        40,
        4,
        2,
        1,
    )
    assert old.cost == 0.004 and old.tool_call_count == 1
    assert not a.warnings


def test_since_prefilter_keeps_working(fixture_home):
    fixture_home("cline")
    ss = list(ClineAdapter().iter_sessions(Filters(since=_utc(2000, 1, 1))))
    assert len(ss) == 7


def test_sdk_events(fixture_home):
    fixture_home("cline")
    a, ss = _sessions()
    events = list(a.iter_events(ss[A]))
    assert [(e.kind, e.role) for e in events] == [
        ("message", "user"),
        ("reasoning", "assistant"),
        ("message", "assistant"),
        ("tool_call", "assistant"),
        ("tool_result", "tool"),
        ("message", "assistant"),
        ("message", "user"),
    ]
    call, result = events[3], events[4]
    assert call.tool_name == "read_files" and call.call_id == "t1" and "src/app.ts" in call.text
    assert result.tool_name == "read_files" and result.call_id == "t1"
    # tokens once per assistant message, on its first event
    assert events[1].tokens_in == 10 and events[2].tokens_in is None and events[3].tokens_in is None
    assert sum(e.tokens_out or 0 for e in events) == 15
    assert events[-1].ts is None  # message without ts
    assert events[1].model == "example-model"

    bev = list(a.iter_events(ss[B]))
    assert bev[2].kind == "tool_result" and bev[2].tool_name == "run_commands"
    assert bev[2].text == "1 passed"
    assert list(a.iter_events(ss[GONE])) == []


def test_legacy_events(fixture_home):
    fixture_home("cline")
    a, ss = _sessions()
    events = list(a.iter_events(ss[LEGACY]))
    assert [e.kind for e in events] == [
        "message",
        "usage",
        "message",
        "tool_call",
        "usage",
        "message",
        "system",
    ]
    assert events[0].role == "user" and events[2].role == "assistant"
    assert events[3].tool_name == "readFile"
    assert sum(e.tokens_in or 0 for e in events) == 300
    assert all(not (e.raw or {}).get("partial") for e in events)
    old = list(a.iter_events(ss[OLD_CLI]))
    assert [(e.kind, e.tool_name) for e in old if e.tool_name] == [
        ("tool_call", "execute_command"),
        ("tool_result", "execute_command"),
    ]


def test_secret_files_never_opened(fixture_home, monkeypatch):
    fixture_home("cline")
    opened: list[str] = []
    real_open, real_io_open = builtins.open, io.open
    real_read_text, real_read_bytes = Path.read_text, Path.read_bytes

    def spy(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def spy_io(file, *args, **kwargs):
        opened.append(str(file))
        return real_io_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy_io)
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, *a, **k: (opened.append(str(self)), real_read_text(self, *a, **k))[1],
    )
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self, *a, **k: (opened.append(str(self)), real_read_bytes(self, *a, **k))[1],
    )

    a = ClineAdapter()
    a.detect()
    dumped = []
    for s in a.iter_sessions(Filters()):
        dumped.append(json.dumps(s.to_dict()))
        for e in a.iter_events(s):
            dumped.append(json.dumps(e.to_dict(include_raw=True), default=str))
    assert opened  # the spy saw the session files
    assert not [
        p for p in opened if p.endswith(("secrets.json", "providers.json", "globalState.json"))
    ]
    assert all("SHOULD-NEVER-BE-READ" not in d for d in dumped)


def test_find_session(fixture_home):
    fixture_home("cline")
    a = ClineAdapter()
    assert find_session([a], "17800001")[1].id == B


def test_cli_end_to_end(fixture_home, capsys):
    fixture_home("cline")
    assert cli.main(["sessions", "--tool", "cline", "--json", "--project", "alice/legacy"]) == 0
    assert {r["id"] for r in _lines(capsys.readouterr().out)} == {MIGRATED, LEGACY}

    assert cli.main(["stats", "--tool", "cline", "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["total"]["sessions"] == 7

    assert cli.main(["search", "readFile", "--tool", "cline", "--json"]) == 0
    assert _lines(capsys.readouterr().out)

    assert cli.main(["sources", "--tool", "cline", "--json"]) == 0
    assert any(r["source"] == "sdk" for r in _lines(capsys.readouterr().out))
