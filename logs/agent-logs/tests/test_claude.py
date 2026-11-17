import json

from agent_logs import cli
from agent_logs.adapters.claude import ClaudeAdapter
from agent_logs.model import Filters
from agent_logs.query import find_session

MAIN = "11111111-1111-1111-1111-111111111111"
OTHER = "33333333-3333-3333-3333-333333333333"


def _sessions():
    a = ClaudeAdapter()
    return a, {s.id: s for s in a.iter_sessions(Filters())}


def _lines(out: str):
    return [json.loads(x) for x in out.splitlines() if x.strip()]


def test_sessions_and_dedup(fixture_home):
    fixture_home("claude")
    a, ss = _sessions()
    # orphaned transcript and journal.jsonl are not sessions
    assert set(ss) == {MAIN, "aaaa", OTHER}
    main = ss[MAIN]
    assert main.project == "C:/Users/alice/proj"
    assert main.title == "List files"
    assert main.model == "claude-opus-5-5"
    assert main.message_count == 2  # user prompt + final text
    assert main.tool_call_count == 1
    # msg_1 spans two lines: counted once with the last usage (out=25)
    assert (main.tokens_in, main.tokens_out) == (15, 32)
    assert (main.tokens_cache_read, main.tokens_cache_write) == (30, 40)
    assert main.cost == 0.12  # last cumulative cost-state
    sub = ss["aaaa"]
    assert sub.parent_id == MAIN and sub.source == "subagent"
    assert sub.title == "Find TODOs" and sub.cost is None
    assert ss[OTHER].title == "Deploy work"
    assert not a.warnings


def test_events(fixture_home):
    fixture_home("claude")
    a, ss = _sessions()
    events = list(a.iter_events(ss[MAIN]))
    assert [e.kind for e in events] == [
        "message",
        "reasoning",
        "tool_call",
        "tool_result",
        "message",
        "turn_end",
        "usage",
        "usage",
        "raw",
    ]
    result = events[3]
    assert result.tool_name == "Bash" and result.call_id == "toolu_1" and "README" in result.text
    assert all("should never be parsed" not in json.dumps(e.raw) for e in events)
    assert all(e.raw.get("type") != "session-owner" for e in events)


def test_find_session(fixture_home):
    fixture_home("claude")
    a = ClaudeAdapter()
    assert find_session([a], "3333")[1].id == OTHER
    assert find_session([a], "claude:aaaa")[1].source == "subagent"


def test_cli_end_to_end(fixture_home, capsys):
    fixture_home("claude")
    assert cli.main(["sessions", "--tool", "claude", "--json", "--project", "alice/proj/sub"]) == 0
    assert [r["id"] for r in _lines(capsys.readouterr().out)] == [OTHER]

    assert cli.main(["search", "readme", "--tool", "claude", "--json"]) == 0
    assert {h["kind"] for h in _lines(capsys.readouterr().out)} == {"tool_result", "message"}

    assert cli.main(["search", "nothing-matches-this", "--tool", "claude"]) == 1
    capsys.readouterr()

    assert cli.main(["stats", "--tool", "claude", "--by", "model", "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["total"]["sessions"] == 3 and st["total"]["cost"] == 0.12

    assert cli.main(["stats", "--tool", "claude", "--by", "tool-name", "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["rows"][0]["key"] == "claude:Bash" and st["rows"][0]["tool_calls"] == 1

    assert cli.main(["show", "1111", "--tool", "claude", "--kind", "tool_call", "--json"]) == 0
    evs = _lines(capsys.readouterr().out)
    assert len(evs) == 1 and evs[0]["tool_name"] == "Bash" and "raw" not in evs[0]

    assert cli.main(["sessions", "--tool", "claude", "--since", "2026-01-15"]) == 0
    out = capsys.readouterr().out
    assert "3333" in out and "1111" not in out

    assert cli.main(["sources", "--tool", "claude", "--json"]) == 0
    src = _lines(capsys.readouterr().out)
    assert src[0]["exists"] and src[0]["count"] == 2
