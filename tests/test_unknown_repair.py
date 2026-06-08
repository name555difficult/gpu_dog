from __future__ import annotations

import unittest
from pathlib import Path

from gpu_monitor.storage.repositories import MonitorRepository
from tests.helpers import TempProject


class UnknownRepairTest(unittest.TestCase):
    def test_repairs_unknown_rows_from_same_pid_known_sample(self) -> None:
        with TempProject() as (_config, database):
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
                            "2026-06-08T09:14:59+08:00",
                            "2026-06-08",
                            2,
                            "GPU-2",
                            736961,
                            "alice",
                            "python",
                            1230,
                            "2026-06-08T09:14:59+08:00",
                        ),
                        (
                            "2026-06-08T09:15:29+08:00",
                            "2026-06-08",
                            2,
                            "GPU-2",
                            736961,
                            "unknown",
                            "[No data]",
                            1080,
                            "2026-06-08T09:15:29+08:00",
                        ),
                    ],
                )

            repairs = MonitorRepository(database, "Asia/Shanghai").repair_unknown_users()

            with database.connect() as conn:
                row = conn.execute(
                    "SELECT username, process_name FROM gpu_process_samples WHERE sample_time = ?",
                    ("2026-06-08T09:15:29+08:00",),
                ).fetchone()

        self.assertEqual(len(repairs), 1)
        self.assertEqual(row["username"], "alice")
        self.assertEqual(row["process_name"], "python")

    def test_does_not_repair_reused_pid_outside_time_window(self) -> None:
        with TempProject() as (_config, database):
            _insert_process_samples(
                database,
                [
                    ("2026-06-07T08:00:00+08:00", "2026-06-07", 0, "GPU-0", 1234, "alice", "train_a", 1000),
                    ("2026-06-08T08:00:00+08:00", "2026-06-08", 0, "GPU-0", 1234, "unknown", "train_b", 1000),
                ],
            )

            repairs = MonitorRepository(database, "Asia/Shanghai").repair_unknown_users()

            with database.connect() as conn:
                row = conn.execute("SELECT username FROM gpu_process_samples WHERE username = 'unknown'").fetchone()

        self.assertEqual(repairs, [])
        self.assertEqual(row["username"], "unknown")

    def test_does_not_repair_same_pid_on_different_gpu(self) -> None:
        with TempProject() as (_config, database):
            _insert_process_samples(
                database,
                [
                    ("2026-06-08T09:14:59+08:00", "2026-06-08", 1, "GPU-1", 1234, "alice", "python", 1000),
                    ("2026-06-08T09:15:29+08:00", "2026-06-08", 2, "GPU-2", 1234, "unknown", "[No data]", 1000),
                ],
            )

            repairs = MonitorRepository(database, "Asia/Shanghai").repair_unknown_users()

        self.assertEqual(repairs, [])

    def test_does_not_repair_when_nearby_pid_has_multiple_candidate_users(self) -> None:
        with TempProject() as (_config, database):
            _insert_process_samples(
                database,
                [
                    ("2026-06-08T09:14:59+08:00", "2026-06-08", 2, "GPU-2", 1234, "alice", "python", 1000),
                    ("2026-06-08T09:15:00+08:00", "2026-06-08", 2, "GPU-2", 1234, "bob", "python", 1000),
                    ("2026-06-08T09:15:29+08:00", "2026-06-08", 2, "GPU-2", 1234, "unknown", "[No data]", 1000),
                ],
            )

            repairs = MonitorRepository(database, "Asia/Shanghai").repair_unknown_users()

        self.assertEqual(repairs, [])

    def test_repair_invalidates_affected_report_caches(self) -> None:
        with TempProject() as (config, database):
            _insert_process_samples(
                database,
                [
                    ("2026-06-08T09:14:59+08:00", "2026-06-08", 2, "GPU-2", 1234, "alice", "python", 1000),
                    ("2026-06-08T09:15:29+08:00", "2026-06-08", 2, "GPU-2", 1234, "unknown", "[No data]", 1000),
                ],
            )
            daily_path = Path(config.reports.cache_dir) / "daily" / "2026-06-08.json"
            weekly_path = Path(config.reports.cache_dir) / "weekly" / "2026-06-08_2026-06-14.json"
            daily_path.parent.mkdir(parents=True, exist_ok=True)
            weekly_path.parent.mkdir(parents=True, exist_ok=True)
            daily_path.write_text("{}", encoding="utf-8")
            weekly_path.write_text("{}", encoding="utf-8")
            with database.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO daily_reports (
                        report_date, status, generated_at, json_path, content_hash,
                        created_at, updated_at
                    )
                    VALUES (?, 'generated', ?, ?, ?, ?, ?)
                    """,
                    ("2026-06-08", "old", str(daily_path), "hash", "old", "old"),
                )
                conn.execute(
                    """
                    INSERT INTO weekly_reports (
                        week_start, week_end, status, generated_at, json_path, content_hash,
                        created_at, updated_at
                    )
                    VALUES (?, ?, 'generated', ?, ?, ?, ?, ?)
                    """,
                    ("2026-06-08", "2026-06-14", "old", str(weekly_path), "hash", "old", "old"),
                )

            repairs = MonitorRepository(database, "Asia/Shanghai").repair_unknown_users()

            with database.connect() as conn:
                daily_count = conn.execute("SELECT COUNT(*) FROM daily_reports").fetchone()[0]
                weekly_count = conn.execute("SELECT COUNT(*) FROM weekly_reports").fetchone()[0]

        self.assertEqual(len(repairs), 1)
        self.assertEqual(daily_count, 0)
        self.assertEqual(weekly_count, 0)
        self.assertFalse(daily_path.exists())
        self.assertFalse(weekly_path.exists())


def _insert_process_samples(database, rows: list[tuple[str, str, int, str, int, str, str, int]]) -> None:
    with database.connect() as conn:
        conn.executemany(
            """
            INSERT INTO gpu_process_samples (
                sample_time, local_date, gpu_index, gpu_uuid, pid, username,
                process_name, used_memory_mb, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row, row[0]) for row in rows],
        )


if __name__ == "__main__":
    unittest.main()
