from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def now_local(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def isoformat(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def local_date(dt: datetime) -> str:
    return dt.date().isoformat()
