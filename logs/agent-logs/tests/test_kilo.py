import json
import sqlite3
from datetime import datetime, timezone

from agent_logs import cli
from agent_logs.adapters.kilo import KiloAdapter
from agent_logs.model import Filters
from agent_logs.query import find_session

MAIN = "ses_0000000000000000000000000y"
SUB = "ses_0000000000000000000000000x"
NEW = "ses_0000000000000000000000000c"
SECRETS = ("FAKE-SECRET", "RkFLRS1TRUNSRVQ")  # plain fake secrets + the base64 data URL body


def _sessions(filters=None):
    a = KiloAdapter()
    return a, {s.id: s for s in a.iter_sessions(filters or Filters())}


def _lines(out: str):
    return [json.loads(x) for x in out.splitlines() if x.strip()]


def _ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, timezone.utc)


def test_detect(fixture_home):
    home = fixture_home("kilo")
    src = {s.source: s for s in KiloAdapter().detect()}
    db = src["db"]
    assert db.exists and db.count == 3
    assert db.path == str(home / ".local" / "share" / "kilo" / "kilo.db")
    assert not src["vscode-globalstorage"].exists


def test_env_override(fixture_home, monkeypatch, tmp_path):
    fixture_home("kilo")
    monkeypatch.setenv("AGENT_LOGS_KILO_DIR", str(tmp_path / "nowhere"))
    a = KiloAdapter()
    assert not a.detect()[0].exists
    assert list(a.iter_sessions(Filters())) == [] and not a.warnings


def test_sessions(fixture_home):
    fixture_home("kilo")
    a, ss = _sessions()
    assert set(ss) == {MAIN, SUB, NEW}
    m = ss[MAIN]
    assert m.source == "main" and m.parent_id is None
    assert m.project == "C:/Users/alice/proj" and m.cwd == "C:/Users/alice/proj/sub"
    assert m.title == "List files" and m.model == "example-model"
    assert m.started_at == _ms(1768003200000)
    assert m.ended_at == _ms(1768003290000)  # max(message.time_updated)
    assert (m.message_count, m.tool_call_count) == (3, 3)
    # session columns (cumulative); tokens_out = output + reasoning
    assert (m.tokens_in, m.tokens_out, m.tokens_cache_read, m.tokens_cache_write) == (
        1500,
        70,
        800,
        40,
    )
    assert m.cost == 0.12
    sub = ss[SUB]
    assert sub.source == "subagent" and sub.parent_id == MAIN
    assert sub.cost == 0.0 and sub.tool_call_count == 0  # recorded zero, not None
    new = ss[NEW]
    assert new.project == "C:/Users/alice/scratch"  # global project -> directory
    assert new.model == "example-model-b"
    assert not a.warnings


def test_since_until_filter(fixture_home):
    fixture_home("kilo")
    _a, ss = _sessions(Filters(since=datetime(2026, 6, 1, tzinfo=timezone.utc)))
    assert set(ss) == {NEW}
    assert ss[NEW].message_count == 2 and ss[NEW].tool_call_count == 0
    _a, ss = _sessions(Filters(until=datetime(2026, 6, 1, tzinfo=timezone.utc)))
    assert set(ss) == {MAIN, SUB}
    assert ss[MAIN].tool_call_count == 3


def test_events(fixture_home):
    fixture_home("kilo")
    a, ss = _sessions()
    events = list(a.iter_events(ss[MAIN]))
    assert [e.kind for e in events] == [
        "message",
        "message",
        "reasoning",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "turn_end",
        "tool_call",
        "tool_result",
        "message",
        "turn_end",
        "raw",
    ]
    assert [e.role for e in events[:2]] == ["user", "user"]
    assert events[1].text == "[file] notes.txt"
    call, result = events[3], events[4]
    assert (
        call.tool_name == "bash"
        and call.call_id == "call_1"
        and json.loads(call.text) == {"command": "ls"}
    )
    assert result.role == "tool" and result.call_id == "call_1" and "README.md" in result.text
    assert result.ts == _ms(1768003215000) and call.ts == _ms(1768003213000)
    err = events[9]
    assert err.tool_name == "read" and err.text == "File not found"
    # tokens once per assistant message, on its first event
    assert events[2].tokens_in == 1000 and events[2].tokens_out == 50 and events[2].cost == 0.1
    assert events[8].tokens_in == 500 and events[8].tokens_cache_write == 40
    assert sum(e.tokens_in or 0 for e in events) == ss[MAIN].tokens_in
    assert sum(e.tokens_out or 0 for e in events) == ss[MAIN].tokens_out
    assert events[10].role == "assistant" and events[10].model == "example-model"

    new = list(a.iter_events(ss[NEW]))
    assert [(e.kind, e.role) for e in new] == [
        ("message", "user"),
        ("system", "system"),
        ("usage", "assistant"),
        ("system", "system"),
    ]
    assert new[2].cost == 0.0 and new[3].text == "APIError: rate limited"


def test_secret_tables_never_read(fixture_home, monkeypatch):
    fixture_home("kilo")
    read_tables: set[str] = set()
    real_connect = sqlite3.connect

    def auth(action, arg1, _arg2, _db, _src):
        if action == sqlite3.SQLITE_READ:
            read_tables.add(arg1)
        return sqlite3.SQLITE_OK

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_authorizer(auth)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    a = KiloAdapter()
    a.detect()
    dumped = []
    for s in a.iter_sessions(Filters()):
        dumped.append(json.dumps(s.to_dict()))
        dumped.extend(json.dumps(e.to_dict(include_raw=True)) for e in a.iter_events(s))
    assert read_tables and read_tables <= {"session", "message", "part", "project", "sqlite_master"}
    blob = "\n".join(dumped)
    assert all(secret not in blob for secret in SECRETS[:1])
    # the data: URL of a file part never becomes searchable text
    assert all(SECRETS[1] not in (json.loads(x).get("text") or "") for x in dumped)


def test_find_session(fixture_home):
    fixture_home("kilo")
    a = KiloAdapter()
    assert find_session([a], "kilo:" + SUB)[1].parent_id == MAIN


def test_cli_end_to_end(fixture_home, capsys):
    fixture_home("kilo")
    assert cli.main(["sessions", "--tool", "kilo", "--json"]) == 0
    rows = _lines(capsys.readouterr().out)
    assert [r["id"] for r in rows][0] == NEW and len(rows) == 3
    assert all("ref" not in r for r in rows)

    assert cli.main(["search", "README", "--tool", "kilo", "--json"]) == 0
    assert {h["kind"] for h in _lines(capsys.readouterr().out)} == {"tool_result", "message"}

    assert cli.main(["search", "FAKE-SECRET", "--tool", "kilo"]) == 1
    capsys.readouterr()

    assert cli.main(["stats", "--tool", "kilo", "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["total"]["sessions"] == 3 and st["total"]["cost"] == 0.12
    assert st["total"]["tokens_in"] == 1700

    assert cli.main(["stats", "--tool", "kilo", "--by", "tool-name", "--json"]) == 0
    keys = {r["key"] for r in json.loads(capsys.readouterr().out)["rows"]}
    assert keys == {"kilo:bash", "kilo:task", "kilo:read"}

    assert cli.main(["sessions", "--tool", "kilo", "--since", "2026-06-01"]) == 0
    out = capsys.readouterr().out
    assert NEW in out and MAIN not in out
