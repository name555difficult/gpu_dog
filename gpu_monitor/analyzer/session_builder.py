from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ActivePoint:
    sample_time: datetime
    memory_mb: float
    process_count: int


@dataclass(frozen=True)
class Session:
    start_time: datetime
    end_time: datetime
    duration_seconds: int


def build_sessions(
    points: list[ActivePoint],
    gap_threshold_seconds: int,
    sample_interval_seconds: int,
    range_end: datetime,
) -> list[Session]:
    if not points:
        return []

    ordered = sorted(points, key=lambda point: point.sample_time)
    sessions: list[Session] = []
    current_start = ordered[0].sample_time
    previous_time = ordered[0].sample_time

    for point in ordered[1:]:
        gap = (point.sample_time - previous_time).total_seconds()
        if gap > gap_threshold_seconds:
            sessions.append(_make_session(current_start, previous_time, sample_interval_seconds, range_end))
            current_start = point.sample_time
        previous_time = point.sample_time

    sessions.append(_make_session(current_start, previous_time, sample_interval_seconds, range_end))
    return sessions


def _make_session(
    start_time: datetime,
    last_sample_time: datetime,
    sample_interval_seconds: int,
    range_end: datetime,
) -> Session:
    end_time = min(last_sample_time + timedelta(seconds=sample_interval_seconds), range_end)
    duration_seconds = max(0, int((end_time - start_time).total_seconds()))
    return Session(start_time=start_time, end_time=end_time, duration_seconds=duration_seconds)
