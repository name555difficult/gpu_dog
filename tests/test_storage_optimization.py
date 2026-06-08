from __future__ import annotations

import unittest

from gpu_monitor.config import parse_config
from gpu_monitor.storage.database import REDUNDANT_INDEXES
from tests.helpers import TempProject


class StorageOptimizationTest(unittest.TestCase):
    def test_lightweight_defaults(self) -> None:
        config = parse_config({})

        self.assertEqual(config.web.refresh_interval_seconds, 60)
        self.assertEqual(config.web.max_issue_items, 5)
        self.assertEqual(config.collector.sample_interval_seconds, 60)
        self.assertTrue(config.storage.cleanup.compact_after_cleanup)
        self.assertEqual(config.storage.cleanup.compact_min_freelist_ratio, 0.15)

    def test_redundant_indexes_are_removed_on_initialize(self) -> None:
        with TempProject() as (_config, database):
            with database.connect() as conn:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_date ON gpu_process_samples(local_date)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_gpu_snapshot_date ON gpu_device_snapshots(local_date)")
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_samples_user_gpu_time
                    ON gpu_process_samples(username, gpu_index, sample_time)
                    """
                )

            database.initialize()

            with database.connect() as conn:
                sample_indexes = {row["name"] for row in conn.execute("PRAGMA index_list(gpu_process_samples)")}
                snapshot_indexes = {row["name"] for row in conn.execute("PRAGMA index_list(gpu_device_snapshots)")}

        self.assertFalse(set(REDUNDANT_INDEXES) & sample_indexes)
        self.assertNotIn("idx_gpu_snapshot_date", snapshot_indexes)
        self.assertIn("idx_samples_time", sample_indexes)
        self.assertIn("idx_gpu_snapshot_time", snapshot_indexes)

    def test_compact_preserves_database_contents(self) -> None:
        with TempProject() as (_config, database):
            with database.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO service_heartbeats (heartbeat_time, status, message, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("2026-06-08T12:00:00+08:00", "ok", "heartbeat", "2026-06-08T12:00:00+08:00"),
                )

            result = database.compact()

            with database.connect() as conn:
                count = conn.execute("SELECT COUNT(*) FROM service_heartbeats").fetchone()[0]

        self.assertEqual(count, 1)
        self.assertIn("before", result)
        self.assertIn("after", result)


if __name__ == "__main__":
    unittest.main()
