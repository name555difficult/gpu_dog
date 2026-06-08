from __future__ import annotations

import unittest
from unittest.mock import patch

from gpu_monitor.cleanup.cleanup_manager import CleanupManager
from tests.helpers import TempProject


class CleanupManagerTest(unittest.TestCase):
    def test_deletes_old_rows(self) -> None:
        with TempProject() as (config, database):
            with database.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO gpu_process_samples (
                        sample_time, local_date, gpu_index, gpu_uuid, pid, username,
                        process_name, used_memory_mb, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("2020-01-01T00:00:00+08:00", "2020-01-01", 0, "GPU-0", 1, "alice", "python", 1000, "2020-01-01T00:00:00+08:00"),
                )

            result = CleanupManager(database, config).run()

            with database.connect() as conn:
                remaining = conn.execute("SELECT COUNT(*) FROM gpu_process_samples").fetchone()[0]

        self.assertEqual(result["gpu_process_samples"], 1)
        self.assertEqual(remaining, 0)
        self.assertIn("storage", result)

    def test_compacts_when_freelist_ratio_crosses_threshold(self) -> None:
        with TempProject() as (config, database):
            with patch.object(database, "storage_stats", return_value={"freelist_ratio": 0.2}), patch.object(
                database,
                "compact",
                return_value={"before": {}, "after": {}},
            ) as compact:
                result = CleanupManager(database, config).run()

        compact.assert_called_once()
        self.assertEqual(result["compact"], {"before": {}, "after": {}})


if __name__ == "__main__":
    unittest.main()
