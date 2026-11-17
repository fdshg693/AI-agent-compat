import json
from datetime import datetime, timezone

import pytest

from agent_logs import cli
from agent_logs.adapters import codex as codex_mod
from agent_logs.adapters.codex import CodexAdapter
from agent_logs.model import Filters, Session

S1 = "00000000-0000-7000-8000-000000000001"
S2 = "00000000-0000-7000-8000-000000000002"
S3 = "00000000-0000-7000-8000-000000000003"
NO_ZSTD = codex_mod._zstd is None


def _sessions():
    a = CodexAdapter()
    return a, {s.id: s for s in a.iter_sessions(Filters())}


def _lines(out: str):
    return [json.loads(x) for x in out.splitlines() if x.strip()]


def _tok(x):
    return (x.tokens_in, x.tokens_out, x.tokens_cache_read, x.tokens_cache_write)


def test_detect(fixture_home):
    home = fixture_home("codex")
    srcs = {s.source: s for s in CodexAdapter().detect()}
    assert set(srcs) == {"sessions", "archived", "state", "session_index", "history"}
    assert srcs["sessions"].exists and srcs["archived"].exists and srcs["state"].exists
    assert srcs["sessions"].path == str(home / ".codex" / "sessions")
    assert srcs["archived"].count == 1
    assert not srcs["history"].exists
    if NO_ZSTD:
        assert srcs["sessions"].count == 2  # .tmp ignored, .zst skipped
        assert "1 .jsonl.zst skipped" in srcs["sessions"].note
    else:
        assert srcs["sessions"].count == 3


def test_env_override(fixture_home, monkeypatch, tmp_path):
    home = fixture_home("codex")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "ignored"))
    assert CodexAdapter().root() == home / ".codex"  # AGENT_LOGS_HOME wins over CODEX_HOME
    monkeypatch.setenv("AGENT_LOGS_CODEX_DIR", str(tmp_path / "x"))
    a = CodexAdapter()
    assert a.root() == tmp_path / "x"
    assert list(a.iter_sessions(Filters())) == [] and not a.warnings


def test_sessions(fixture_home):
    fixture_home("codex")
    a, ss = _sessions()
    assert set(ss) == {S1, S2, S3}  # no session for the .tmp file or the DB-only thread
    s1 = ss[S1]
    assert s1.source == "sessions" and s1.parent_id is None
    assert s1.project == "C:/work/demo" and s1.cwd == "C:\\work\\demo"
    assert s1.model == "gpt-fake-codex-mini"  # last turn_context
    assert s1.title == "Fix the demo build"  # threads.title
    assert s1.started_at == datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=timezone.utc)
    assert s1.ended_at == datetime(2026, 1, 2, 3, 5, 5, tzinfo=timezone.utc)
    # 2 user + 2 assistant; developer / environment_context / event_msg duplicates excluded
    assert s1.message_count == 4 and s1.tool_call_count == 2
    # last cumulative total_token_usage: input 250 - cached 100
    assert _tok(s1) == (150, 50, 100, None)
    assert s1.cost is None

    s2 = ss[S2]
    assert s2.parent_id == S1 and s2.project == "C:/work/demo/sub"
    assert s2.title == "TODO sweep"  # session_index (last line) beats threads.name
    assert s2.message_count == 2 and s2.tool_call_count == 1
    assert _tok(s2) == (50, 10, 30, None)  # last thread_token_usage

    s3 = ss[S3]
    assert s3.source == "archived" and s3.project == "/home/bob/proj"
    assert s3.title == "hello archive"  # first user message, first line
    assert _tok(s3) == (10, 2, 0, None)
    if NO_ZSTD:
        assert len(a.warnings) == 1 and ".jsonl.zst" in a.warnings[0]
        list(a.iter_sessions(Filters()))
        assert len(a.warnings) == 1  # warned once
    else:
        assert any("000000000004" in w for w in a.warnings)  # bogus bytes -> per-file warning


def test_events_legacy(fixture_home):
    fixture_home("codex")
    a, ss = _sessions()
    events = list(a.iter_events(ss[S1]))
    assert [(e.kind, e.role) for e in events] == [
        ("raw", None),  # task_started
        ("system", "system"),  # developer message
        ("system", "system"),  # <environment_context>
        ("message", "user"),
        ("reasoning", "assistant"),
        ("tool_call", "assistant"),
        ("tool_result", "tool"),
        ("message", "assistant"),
        ("usage", None),
        ("turn_end", "system"),
        ("message", "user"),
        ("tool_call", "assistant"),
        ("tool_result", "tool"),
        ("message", "assistant"),
        ("usage", None),
        ("turn_end", "system"),
        ("summary", "system"),
        ("raw", None),  # unknown record type
    ]
    texts = [e.text for e in events if e.kind == "message"]
    assert texts == [
        "Fix the build in demo",
        "Fixed the missing semicolon.",
        "Now run the tests",
        "All tests pass.",
    ]  # each once
    call, result = events[5], events[6]
    assert call.tool_name == "shell" and call.call_id == "call_1"
    assert call.text == '{"command":["npm","run","build"]}'
    assert call.model == "gpt-fake-codex"
    assert result.tool_name == "shell" and result.call_id == "call_1"
    assert "missing semicolon" in result.text
    assert events[11].text == "not-json{" and events[12].text == "3 passed"
    assert events[13].model == "gpt-fake-codex-mini"
    assert events[4].text == "Looking at the build script"
    usage = [e for e in events if e.kind == "usage"]
    assert [_tok(e) for e in usage] == [(60, 20, 40, None), (90, 30, 60, None)]
    # per-event deltas add up to the cumulative session total
    assert tuple(sum(_tok(e)[i] for e in usage) for i in range(3)) == _tok(ss[S1])[:3]
    dumped = json.dumps([e.to_dict() for e in events])
    for secret in (
        "FAKE-BASE-INSTRUCTIONS",
        "FAKE-ENCRYPTED",
        "FAKE-TOKEN",
        "FAKE-PLAN",
        "FAKE-AUTH",
    ):
        assert secret not in dumped
    assert all(e.raw.get("type") != "session_meta" for e in events)


def test_events_token_usage_record(fixture_home):
    fixture_home("codex")
    a, ss = _sessions()
    events = list(a.iter_events(ss[S2]))
    assert [e.kind for e in events] == [
        "message",
        "tool_call",
        "tool_result",
        "usage",
        "usage",
        "message",
        "usage",
        "usage",
        "turn_end",
    ]  # broken last line skipped
    assert events[1].tool_name == "apply_patch" and events[2].tool_name == "apply_patch"
    usage = [e for e in events if e.kind == "usage"]
    # token_usage_record carries per-response usage; token_count events carry none
    assert [_tok(e) for e in usage] == [
        (40, 7, 10, None),
        (None, None, None, None),
        (10, 3, 20, None),
        (None, None, None, None),
    ]


@pytest.mark.skipif(not NO_ZSTD, reason="skip path only exists below Python 3.14")
def test_zst_skipped_in_events(fixture_home):
    fixture_home("codex")
    a = CodexAdapter()
    files = [p for p, _ in a._rollouts() if p.name.endswith(".zst")]
    assert len(files) == 1
    s = Session(id="z", tool="codex", path=str(files[0]), ref=files[0])
    assert list(a.iter_events(s)) == [] and "3.14" in a.warnings[0]


def test_cli(fixture_home, capsys):
    fixture_home("codex")
    assert cli.main(["sessions", "--tool", "codex", "--json", "--project", "work/demo/sub"]) == 0
    assert [r["id"] for r in _lines(capsys.readouterr().out)] == [S2]

    assert cli.main(["search", "semicolon", "--tool", "codex", "--json"]) == 0
    hits = _lines(capsys.readouterr().out)
    assert [h["kind"] for h in hits] == ["tool_result", "message"]  # no legacy duplicates

    assert cli.main(["stats", "--tool", "codex", "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["total"]["sessions"] == 3
    assert st["total"]["tokens_in"] == 150 + 50 + 10

    assert cli.main(["sources", "--tool", "codex", "--json"]) == 0
    assert len(_lines(capsys.readouterr().out)) == 5
