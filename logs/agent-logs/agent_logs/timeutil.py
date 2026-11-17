"""Timestamp parsing into timezone-aware UTC datetimes.

Accepted inputs: ISO 8601 strings (``Z`` / ``+00:00`` / up to 9 fractional digits),
epoch seconds or milliseconds (int/float/numeric string), protobuf-style
``{"seconds": ..., "nanos": ...}`` dicts, and the Cursor transcript tag
``Weekday, Mon D, YYYY, H:MM AM (UTC+9)`` (parsed without locale). Antigravity's
``0001-01-01...`` zero value is treated as unset (``None``).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

UTC = timezone.utc

_ISO_FRACTION = re.compile(r"(\.\d+)")
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
_CURSOR_TS = re.compile(
    r"(?:[A-Za-z]+,\s*)?(?P<mon>[A-Za-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4}),?\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s*(?P<ampm>AM|PM|am|pm)?"
    r"\s*(?:\((?:UTC|GMT)(?P<off>[+-]\d{1,2})(?::?(?P<offm>\d{2}))?\))?"
)
# epoch values above this are milliseconds (year 33658 in seconds)
_MS_THRESHOLD = 1e12


def parse_ts(value: Any) -> datetime | None:
    """Best-effort conversion to an aware UTC datetime; ``None`` when unknown."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _from_epoch(float(value))
    if isinstance(value, dict):
        if "seconds" in value:
            try:
                secs = float(value.get("seconds") or 0) + float(value.get("nanos") or 0) / 1e9
            except (TypeError, ValueError):
                return None
            return None if secs <= 0 else _from_epoch(secs)
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return _from_epoch(float(s))
        if s.startswith("0001-01-01"):
            return None
        return _parse_iso(s) or parse_cursor_ts(s)
    return None


def _from_epoch(x: float) -> datetime | None:
    if x <= 0:
        return None
    if x > _MS_THRESHOLD:
        x /= 1000.0
    try:
        return datetime.fromtimestamp(x, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _parse_iso(s: str) -> datetime | None:
    t = s.replace("Z", "+00:00").replace("z", "+00:00")
    if " " in t and "T" not in t:
        t = t.replace(" ", "T", 1)
    # Python <3.11-safe: trim fractions to 6 digits (7-digit .NET / 9-digit Go values)
    t = _ISO_FRACTION.sub(lambda m: m.group(1)[:7], t, count=1)
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def parse_cursor_ts(s: str) -> datetime | None:
    """Parse ``Tuesday, Nov 17, 2026, 9:05 AM (UTC+9)``-style text (locale-independent)."""
    m = _CURSOR_TS.search(s)
    if not m:
        return None
    mon = _MONTHS.get(m.group("mon").lower()[:3])
    if not mon:
        return None
    hour = int(m.group("hour"))
    ampm = (m.group("ampm") or "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    off = timedelta(0)
    if m.group("off"):
        sign = -1 if m.group("off").startswith("-") else 1
        off = sign * timedelta(hours=abs(int(m.group("off"))), minutes=int(m.group("offm") or 0))
    try:
        local = datetime(
            int(m.group("year")),
            mon,
            int(m.group("day")),
            hour,
            int(m.group("minute")),
            int(m.group("second") or 0),
            tzinfo=timezone(off),
        )
    except ValueError:
        return None
    return local.astimezone(UTC)


_RELATIVE = re.compile(r"^(\d+)\s*([smhdw])$")


def parse_cli_time(text: str, *, now: datetime | None = None) -> datetime:
    """``--since`` / ``--until`` value: ISO date/datetime or relative ``30m``/``12h``/``7d``/``2w``.

    A naive ISO value is interpreted in local time.
    """
    s = text.strip()
    m = _RELATIVE.match(s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {
            "s": timedelta(seconds=n),
            "m": timedelta(minutes=n),
            "h": timedelta(hours=n),
            "d": timedelta(days=n),
            "w": timedelta(weeks=n),
        }[unit]
        return (now or datetime.now(UTC)) - delta
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"invalid time: {text!r} (use ISO 8601 or e.g. 7d / 12h)") from None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # local time
    return dt.astimezone(UTC)
