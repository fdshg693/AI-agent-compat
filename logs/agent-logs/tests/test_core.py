from datetime import datetime, timezone

from agent_logs.paths import normalize_path, project_matches
from agent_logs.timeutil import parse_cli_time, parse_ts

UTC = timezone.utc


def test_parse_ts_variants():
    exp = datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_ts("2026-01-01T00:00:00.000Z") == exp
    assert parse_ts("2026-01-01T00:00:00.0000000+00:00") == exp
    assert parse_ts("2026-01-01T09:00:00.123456789+09:00").replace(microsecond=0) == exp
    assert parse_ts(1767225600) == exp
    assert parse_ts(1767225600000) == exp
    assert parse_ts("1767225600000") == exp
    assert parse_ts({"seconds": 1767225600, "nanos": 0}) == exp
    assert parse_ts("0001-01-01T00:00:00Z") is None
    assert parse_ts(0) is None and parse_ts(None) is None and parse_ts("garbage") is None


def test_parse_cursor_timestamp_tag():
    assert parse_ts("Thursday, Jan 1, 2026, 9:00 AM (UTC+9)") == datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_ts("Wed, Dec 31, 2025, 12:30 PM (UTC-5)") == datetime(
        2025, 12, 31, 17, 30, tzinfo=UTC
    )


def test_parse_cli_time_relative():
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert parse_cli_time("7d", now=now) == datetime(2026, 1, 3, tzinfo=UTC)
    assert parse_cli_time("2026-01-01T00:00:00Z") == datetime(2026, 1, 1, tzinfo=UTC)


def test_normalize_path():
    assert normalize_path("c:\\Users\\alice\\proj\\") == "C:/Users/alice/proj"
    assert normalize_path("file:///c%3A/Users/alice/proj") == "C:/Users/alice/proj"
    assert normalize_path("/home/alice/proj/") == "/home/alice/proj"
    assert normalize_path("C:\\") == "C:/"
    assert normalize_path("") is None
    assert project_matches("C:/Users/alice/proj", "c:\\users\\alice")
    assert not project_matches(None, "x")
