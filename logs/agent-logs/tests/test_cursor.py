import json
from datetime import datetime, timezone

from agent_logs import cli
from agent_logs.adapters.cursor import CursorAdapter
from agent_logs.model import Filters

CLI_ID = "c1c1c1c1-0000-4000-8000-000000000001"
SUB_ID = "d2d2d2d2-0000-4000-8000-000000000002"
IDE_ID = "e3e3e3e3-0000-4000-8000-000000000003"
NOMETA_ID = "f4f4f4f4-0000-4000-8000-000000000004"
WS_ID = "a5a5a5a5-0000-4000-8000-000000000005"
STORE_ID = "b7b7b7b7-0000-4000-8000-000000000007"
UTC = timezone.utc


def _sessions():
    a = CursorAdapter()
    return a, {s.id: s for s in a.iter_sessions(Filters())}


def _lines(out: str):
    return [json.loads(x) for x in out.splitlines() if x.strip()]


def test_detect(fixture_home):
    fixture_home("cursor")
    src = {s.source: s for s in CursorAdapter().detect()}
    assert src["transcript"].exists and src["transcript"].count == 6
    assert src["cli"].exists and src["cli"].count == 3
    assert src["ide"].exists and src["ide"].count == 2  # non-JSON header row skipped


def test_sessions(fixture_home):
    fixture_home("cursor")
    a, ss = _sessions()
    assert set(ss) == {CLI_ID, SUB_ID, IDE_ID, NOMETA_ID, WS_ID, STORE_ID}

    c = ss[CLI_ID]
    assert c.source == "cli" and c.project == "C:/Users/alice/proj"
    assert c.title == "Summarize README"  # meta.json title beats store.db name
    assert c.model == "gpt-9-codex"
    assert c.started_at == datetime(2025, 11, 16, 0, 0, tzinfo=UTC)
    assert c.ended_at == datetime(2025, 11, 16, 1, 0, tzinfo=UTC)
    assert (c.message_count, c.tool_call_count) == (2, 2)

    sub = ss[SUB_ID]
    assert sub.source == "subagent" and sub.parent_id == CLI_ID
    assert sub.project == "C:/Users/alice/proj"  # enc dir mapped to a cwd known from B
    assert sub.title == "grep TODO" and sub.ended_at is not None

    n = ss[NOMETA_ID]
    assert n.source == "transcript" and n.project == "C:/Users/alice/proj"
    assert n.title == "Fix the flaky test"
    assert n.started_at == datetime(2026, 11, 16, 0, 0, tzinfo=UTC)  # <timestamp> tag, UTC+9
    assert n.ended_at == datetime(2026, 11, 16, 1, 30, tzinfo=UTC)
    assert (n.message_count, n.tool_call_count) == (4, 1)  # broken last line dropped

    ide = ss[IDE_ID]
    assert ide.source == "ide" and ide.project == "C:/Users/alice/web"
    assert ide.title == "Dark mode" and ide.model == "claude-fake-1"
    assert ide.started_at == datetime.fromtimestamp(1794888300, UTC)

    ws = ss[WS_ID]
    assert ws.source == "ide" and ws.project == "C:/Users/alice/docs"  # workspace.json
    assert ws.title == "Proofread the guide" and ws.model is None

    st = ss[STORE_ID]  # store.db only: cwd from md5(cwd) group dir, not the dir name
    assert st.source == "cli" and st.project == "C:/Users/alice/proj"
    assert st.title == "Store only chat" and st.model is None
    assert st.started_at == datetime(2025, 11, 18, 0, 0, tzinfo=UTC)

    for s in ss.values():
        assert s.tokens_in is None and s.tokens_out is None and s.cost is None
        assert s.tokens_cache_read is None and s.tokens_cache_write is None
    assert not a.warnings


def test_events(fixture_home):
    fixture_home("cursor")
    a, ss = _sessions()
    ev = list(a.iter_events(ss[CLI_ID]))
    assert [(e.kind, e.role) for e in ev] == [
        ("message", "user"),
        ("tool_call", "assistant"),
        ("tool_call", "assistant"),
        ("message", "assistant"),
        ("turn_end", "system"),
    ]
    assert [e.tool_name for e in ev if e.kind == "tool_call"] == ["Read", "Task"]
    assert "README.md" in ev[1].text
    # assistant lines inherit the user line's tag time
    assert {e.ts for e in ev} == {datetime(2025, 11, 16, 0, 0, tzinfo=UTC)}

    ev = list(a.iter_events(ss[NOMETA_ID]))
    turn_ends = [e for e in ev if e.kind == "turn_end"]
    assert turn_ends[0].text == "error: rate limited"
    assert ev[-1].ts == datetime(2026, 11, 16, 1, 30, tzinfo=UTC)


def test_secrets_never_emitted(fixture_home, capsys):
    fixture_home("cursor")
    a, ss = _sessions()
    dumped = json.dumps([s.to_dict() for s in ss.values()])
    for s in ss.values():
        dumped += json.dumps([e.to_dict(include_raw=True) for e in a.iter_events(s)])
    assert cli.main(["sessions", "--tool", "cursor", "--json"]) == 0
    dumped += capsys.readouterr().out
    assert cli.main(["sources", "--tool", "cursor", "--json"]) == 0
    dumped += capsys.readouterr().out
    for needle in (
        "FAKE-KEY-SHOULD-NOT-LEAK",
        "FAKE-SECRET-SHOULD-NOT-LEAK",
        "EncryptionKey",
        "BUBBLE-BODY-NOT-READ",
        "Store name",
    ):
        assert needle not in dumped


def test_cli_end_to_end(fixture_home, capsys):
    fixture_home("cursor")
    assert cli.main(["sessions", "--tool", "cursor", "--json", "--project", "alice/web"]) == 0
    assert [r["id"] for r in _lines(capsys.readouterr().out)] == [IDE_ID]

    assert cli.main(["search", "flaky", "--tool", "cursor", "--json"]) == 0
    hits = _lines(capsys.readouterr().out)
    assert hits and all(h["session_id"] == NOMETA_ID for h in hits)

    assert cli.main(["stats", "--tool", "cursor", "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["total"]["sessions"] == 6 and st["total"]["tool_calls"] == 5
    assert st["total"].get("tokens_in") is None and st["total"].get("cost") is None

    assert cli.main(["stats", "--tool", "cursor", "--by", "tool-name", "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert {r["key"] for r in st["rows"]} >= {"cursor:Read", "cursor:Task", "cursor:Shell"}
