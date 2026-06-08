from __future__ import annotations

import unittest

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
                            "yzt",
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
        self.assertEqual(row["username"], "yzt")
        self.assertEqual(row["process_name"], "python")


if __name__ == "__main__":
    unittest.main()
