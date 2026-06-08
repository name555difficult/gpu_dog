from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from gpu_monitor.analyzer.session_builder import ActivePoint, build_sessions, merge_sessions


class SessionBuilderTest(unittest.TestCase):
    def test_splits_on_large_gap(self) -> None:
        tz = ZoneInfo("Asia/Shanghai")
        base = datetime(2026, 6, 7, 10, 0, tzinfo=tz)
        points = [
            ActivePoint(base, 1000, 1),
            ActivePoint(base + timedelta(seconds=30), 1000, 1),
            ActivePoint(base + timedelta(seconds=400), 1000, 1),
        ]

        sessions = build_sessions(points, gap_threshold_seconds=300, sample_interval_seconds=30, range_end=base + timedelta(hours=1))

        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0].duration_seconds, 60)
        self.assertEqual(sessions[1].duration_seconds, 30)

    def test_merges_short_gap_sessions_preserving_active_duration(self) -> None:
        tz = ZoneInfo("Asia/Shanghai")
        base = datetime(2026, 6, 7, 10, 0, tzinfo=tz)
        points = [
            ActivePoint(base, 1000, 1),
            ActivePoint(base + timedelta(minutes=1), 1000, 1),
            ActivePoint(base + timedelta(minutes=30), 1000, 1),
        ]

        raw_sessions = build_sessions(
            points,
            gap_threshold_seconds=300,
            sample_interval_seconds=60,
            range_end=base + timedelta(hours=2),
        )
        sessions = merge_sessions(raw_sessions, merge_gap_threshold_seconds=3600)

        self.assertEqual(len(raw_sessions), 2)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].start_time, base)
        self.assertEqual(sessions[0].end_time, base + timedelta(minutes=31))
        self.assertEqual(sessions[0].duration_seconds, 180)
        self.assertNotEqual(sessions[0].duration_seconds, int((sessions[0].end_time - sessions[0].start_time).total_seconds()))

    def test_merges_gap_equal_to_threshold(self) -> None:
        tz = ZoneInfo("Asia/Shanghai")
        base = datetime(2026, 6, 7, 10, 0, tzinfo=tz)
        points = [
            ActivePoint(base, 1000, 1),
            ActivePoint(base + timedelta(hours=1, minutes=1), 1000, 1),
        ]

        raw_sessions = build_sessions(
            points,
            gap_threshold_seconds=300,
            sample_interval_seconds=60,
            range_end=base + timedelta(hours=2),
        )
        sessions = merge_sessions(raw_sessions, merge_gap_threshold_seconds=3600)

        self.assertEqual(len(raw_sessions), 2)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].duration_seconds, 120)

    def test_does_not_merge_gap_above_threshold(self) -> None:
        tz = ZoneInfo("Asia/Shanghai")
        base = datetime(2026, 6, 7, 10, 0, tzinfo=tz)
        points = [
            ActivePoint(base, 1000, 1),
            ActivePoint(base + timedelta(hours=1, minutes=2), 1000, 1),
        ]

        raw_sessions = build_sessions(
            points,
            gap_threshold_seconds=300,
            sample_interval_seconds=60,
            range_end=base + timedelta(hours=2),
        )
        sessions = merge_sessions(raw_sessions, merge_gap_threshold_seconds=3600)

        self.assertEqual(len(raw_sessions), 2)
        self.assertEqual(len(sessions), 2)


if __name__ == "__main__":
    unittest.main()
