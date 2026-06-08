from __future__ import annotations

try:
    from zoneinfo import ZoneInfo
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.8
    from backports.zoneinfo import ZoneInfo

__all__ = ["ZoneInfo"]
