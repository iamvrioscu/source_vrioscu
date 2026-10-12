from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo('Asia/Kolkata')
except ImportError:
    IST = timezone(timedelta(hours=5, minutes=30), 'Asia/Kolkata')
except KeyError:
    # Windows installations without a system IANA database. India has no DST.
    IST = timezone(timedelta(hours=5, minutes=30), 'Asia/Kolkata')


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return iso(utcnow())


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    # Historical schema and all writers use UTC, including legacy naive values.
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def display_ist(value):
    if not value:
        return '—'
    try:
        return parse_iso(value).astimezone(IST).strftime('%d %b %Y, %I:%M:%S %p IST')
    except (TypeError, ValueError):
        return 'Invalid timestamp'


def ist_day_bounds(today, days=1):
    start = datetime.combine(today - timedelta(days=days-1), datetime.min.time(), IST)
    end = datetime.combine(today + timedelta(days=1), datetime.min.time(), IST)
    return iso(start), iso(end)


def plus(minutes: int = 0, hours: int = 0) -> str:
    return iso(utcnow() + timedelta(minutes=minutes, hours=hours))
