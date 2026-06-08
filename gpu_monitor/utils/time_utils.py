from __future__ import annotations

from datetime import date, datetime, time, timedelta

from gpu_monitor.utils.zoneinfo_compat import ZoneInfo


def now_local(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def isoformat(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def local_date(dt: datetime) -> str:
    return dt.date().isoformat()


def parse_local_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def day_bounds(day: str | date, timezone: str) -> tuple[datetime, datetime]:
    target = parse_local_date(day) if isinstance(day, str) else day
    tz = ZoneInfo(timezone)
    start = datetime.combine(target, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


def week_bounds(day: str | date, timezone: str) -> tuple[date, date, datetime, datetime]:
    target = parse_local_date(day) if isinstance(day, str) else day
    week_start = target - timedelta(days=target.weekday())
    week_end = week_start + timedelta(days=6)
    start_dt, _ = day_bounds(week_start, timezone)
    _, end_dt = day_bounds(week_end, timezone)
    return week_start, week_end, start_dt, end_dt


def date_range(start: date, days: int) -> list[date]:
    return [start + timedelta(days=offset) for offset in range(days)]


def seconds_between(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds()))


def human_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"
