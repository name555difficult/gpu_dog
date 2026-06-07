from __future__ import annotations

import unittest

from gpu_monitor.analyzer.daily_analyzer import DailyAnalyzer
from tests.helpers import TempProject, seed_sample_data


class DailyAnalyzerTest(unittest.TestCase):
    def test_aggregates_processes_before_memory_stats(self) -> None:
        with TempProject() as (config, database):
            seed_sample_data(database)

            summary = DailyAnalyzer(database, config).analyze("2026-06-07")

        self.assertEqual(summary["overview"]["active_user_count"], 1)
        self.assertEqual(summary["overview"]["used_gpu_count"], 1)
        self.assertEqual(summary["overview"]["unknown_process_count"], 1)
        entry = summary["user_gpu"][0]
        self.assertEqual(entry["username"], "alice")
        self.assertEqual(entry["active_sample_count"], 2)
        self.assertEqual(entry["duration_seconds"], 60)
        self.assertEqual(entry["avg_memory_mb"], 3500)
        self.assertEqual(entry["peak_memory_mb"], 4000)


if __name__ == "__main__":
    unittest.main()
