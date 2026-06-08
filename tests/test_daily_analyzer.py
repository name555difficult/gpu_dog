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

    def test_merges_short_gap_sessions_without_counting_idle_gap(self) -> None:
        with TempProject() as (config, database):
            with database.connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO gpu_process_samples (
                        sample_time, local_date, gpu_index, gpu_uuid, pid, username,
                        process_name, used_memory_mb, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            "2026-06-07T10:00:00+08:00",
                            "2026-06-07",
                            0,
                            "GPU-0",
                            101,
                            "alice",
                            "python",
                            1000,
                            "2026-06-07T10:00:00+08:00",
                        ),
                        (
                            "2026-06-07T10:00:30+08:00",
                            "2026-06-07",
                            0,
                            "GPU-0",
                            101,
                            "alice",
                            "python",
                            1000,
                            "2026-06-07T10:00:30+08:00",
                        ),
                        (
                            "2026-06-07T10:30:30+08:00",
                            "2026-06-07",
                            0,
                            "GPU-0",
                            101,
                            "alice",
                            "python",
                            1000,
                            "2026-06-07T10:30:30+08:00",
                        ),
                        (
                            "2026-06-07T10:31:00+08:00",
                            "2026-06-07",
                            0,
                            "GPU-0",
                            101,
                            "alice",
                            "python",
                            1000,
                            "2026-06-07T10:31:00+08:00",
                        ),
                    ],
                )

            summary = DailyAnalyzer(database, config).analyze("2026-06-07")

        entry = summary["user_gpu"][0]
        self.assertEqual(entry["duration_seconds"], 120)
        self.assertEqual(len(entry["sessions"]), 1)
        self.assertEqual(entry["sessions"][0]["start_time"], "2026-06-07T10:00:00+08:00")
        self.assertEqual(entry["sessions"][0]["end_time"], "2026-06-07T10:31:30+08:00")
        self.assertEqual(entry["sessions"][0]["duration_seconds"], 120)
        self.assertEqual(summary["overview"]["total_usage_seconds"], 120)
        self.assertEqual(summary["overview"]["session_merge_gap_threshold_seconds"], 3600)


if __name__ == "__main__":
    unittest.main()
