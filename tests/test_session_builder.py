from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from gpu_monitor.analyzer.session_builder import ActivePoint, build_sessions


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


if __name__ == "__main__":
    unittest.main()
