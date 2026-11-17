import json
from datetime import datetime, timezone

from agent_logs import cli
from agent_logs.adapters.antigravity import AntigravityAdapter
from agent_logs.model import Filters

A = "aaaaaaaa-0000-4000-8000-000000000001"  # main root, transcript_full + summary + rename
B = "bbbbbbbb-0000-4000-8000-000000000002"  # summary only (subagent of A)
C = "cccccccc-0000-4000-8000-000000000003"  # summary in main and cli roots (dup)
D = "dddddddd-0000-4000-8000-000000000004"  # ide root, truncated transcript.jsonl only
E = "eeeeeeee-0000-4000-8000-000000000005"  # conversations/<id>.db only (not decoded)
SECRETS = ("FAKE-CSRF-SHOULD-NOT-APPEAR", "FAKE-INSTALLATION-ID")


def _sessions():
    a = AntigravityAdapter()
    return a, {s.id: s for s in a.iter_sessions(Filters())}


def _lines(out: str):
    return [json.loads(x) for x in out.splitlines() if x.strip()]


def test_detect(fixture_home):
    fixture_home("antigravity")
    src = {s.source: s for s in AntigravityAdapter().detect()}
    assert src["antigravity/summaries"].count == 3
    assert src["antigravity-cli/summaries"].count == 1
    assert not src["antigravity-ide/summaries"].exists
    assert src["antigravity/transcripts"].count == 1
    assert src["antigravity-ide/transcripts"].count == 1
    assert src["antigravity-ide/conversations"].count == 1
    assert "not decoded" in src["antigravity-ide/conversations"].note


def test_sessions_dedup_and_fallback(fixture_home):
    home = fixture_home("antigravity")
    a, ss = _sessions()
    assert set(ss) == {A, B, C, D}  # E has only a protobuf DB
    s = ss[A]
    assert s.source == "antigravity"
    assert s.project == "C:/Users/alice/proj"
    assert s.title == 'Renamed "README" chat'  # annotation beats summary title
    assert s.model == "example-model-2"
    assert (s.message_count, s.tool_call_count) == (2, 2)
    assert (s.tokens_in, s.tokens_out, s.tokens_cache_read) == (2710, 100, 100)
    assert s.tokens_cache_write is None and s.cost is None
    assert s.started_at == datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc)
    assert s.ended_at.isoformat().startswith("2026-01-10T09:00:10.123456")
    # metadata-only fallback
    b = ss[B]
    assert b.parent_id == A and b.title == "Research subagent"
    assert b.project is None and b.started_at is None
    assert b.message_count is None and b.tokens_in is None
    assert list(a.iter_events(b)) == []
    # duplicated across roots: newest summary wins
    c = ss[C]
    assert c.source == "antigravity" and c.title == "Deploy the site"  # empty title -> preview
    assert c.project == "D:/work/site"
    # truncated transcript fallback in the old IDE root
    d = ss[D]
    assert d.source == "antigravity-ide" and d.path.endswith("transcript.jsonl")
    assert (d.tokens_in, d.tokens_out, d.tokens_cache_read) == (700, 35, 5)
    assert not a.warnings
    # nothing written next to the source DBs
    assert not list(home.rglob("*-wal")) and not list(home.rglob("*-shm"))


def test_events(fixture_home):
    fixture_home("antigravity")
    a, ss = _sessions()
    evs = list(a.iter_events(ss[A]))
    assert [e.kind for e in evs] == [
        "message",
        "reasoning",
        "tool_call",
        "tool_call",
        "tool_result",
        "tool_result",
        "message",
        "system",
        "summary",
        "usage",
    ]
    assert [e.role for e in evs[:3]] == ["user", "assistant", "assistant"]
    # tokens once per PLANNER_RESPONSE, on its first event
    assert (evs[1].tokens_in, evs[2].tokens_in, evs[3].tokens_in) == (1200, None, None)
    assert evs[9].tokens_in == 10 and evs[9].model == "example-model-2"
    call, res = evs[2], evs[4]
    assert call.tool_name == "read_file" and json.loads(call.text) == {"path": "README.md"}
    assert res.role == "tool" and res.tool_name == "read_file" and res.call_id == call.call_id
    assert evs[5].tool_name == "run_command" and evs[5].call_id == evs[3].call_id
    blob = json.dumps([e.to_dict(include_raw=True) for e in evs])
    assert not any(x in blob for x in SECRETS)
    d = list(a.iter_events(ss[D]))
    assert [e.kind for e in d] == ["message", "tool_call", "tool_result", "message"]
    assert d[2].tool_name == "edit_file"


def test_cli(fixture_home, capsys):
    fixture_home("antigravity")
    assert cli.main(["sessions", "--tool", "antigravity", "--json", "--project", "alice"]) == 0
    assert [r["id"] for r in _lines(capsys.readouterr().out)] == [A]

    assert cli.main(["show", A, "--tool", "antigravity", "--raw", "--json"]) == 0
    out = capsys.readouterr().out
    assert len(_lines(out)) == 10 and not any(x in out for x in SECRETS)

    assert cli.main(["stats", "--tool", "antigravity", "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["total"]["sessions"] == 4

    assert cli.main(["sources", "--tool", "antigravity", "--json"]) == 0
    out = capsys.readouterr().out
    assert len(_lines(out)) == 9 and not any(x in out for x in SECRETS)
