from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from gpu_monitor.config import Config, parse_config
from gpu_monitor.storage.database import Database


def make_config(root: Path) -> Config:
    return parse_config(
        {
            "app": {"server_name": "test-server", "timezone": "Asia/Shanghai"},
            "web": {"enabled": True, "host": "127.0.0.1", "port": 0, "refresh_interval_seconds": 30},
            "collector": {
                "backend": "nvidia-smi",
                "sample_interval_seconds": 30,
                "active_memory_threshold_mb": 100,
                "command_timeout_seconds": 10,
            },
            "session": {"gap_threshold_seconds": 300},
            "heartbeat": {"interval_seconds": 60, "missing_threshold_seconds": 300},
            "reports": {
                "cache_dir": str(root / "reports"),
                "daily": {"generate_time": "00:05"},
                "weekly": {"generate_day": "monday", "generate_time": "00:10"},
            },
            "storage": {
                "sqlite_path": str(root / "monitor.db"),
                "cleanup": {
                    "raw_retention_days": 3,
                    "gpu_snapshot_retention_days": 3,
                    "daily_cache_retention_days": 14,
                    "weekly_cache_retention_weeks": 12,
                    "error_log_retention_days": 7,
                    "heartbeat_retention_days": 7,
                },
            },
            "users": {"alias": {"alice": "Alice", "unknown": "Unknown"}},
        }
    )


class TempProject:
    def __enter__(self) -> tuple[Config, Database]:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = make_config(self.root)
        self.database = Database(self.config.storage.sqlite_path)
        self.database.initialize()
        return self.config, self.database

    def __exit__(self, *_args: object) -> None:
        self.tmp.cleanup()


def seed_sample_data(database: Database) -> None:
    with database.connect() as conn:
        conn.executemany(
            """
            INSERT INTO gpu_device_snapshots (
                sample_time, local_date, gpu_index, gpu_uuid, gpu_name,
                total_memory_mb, gpu_util_percent, memory_util_percent, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-06-07T10:00:00+08:00", "2026-06-07", 0, "GPU-0", "Test GPU", 24000, 50, 40, "2026-06-07T10:00:00+08:00"),
                ("2026-06-07T10:00:30+08:00", "2026-06-07", 0, "GPU-0", "Test GPU", 24000, 60, 45, "2026-06-07T10:00:30+08:00"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO gpu_process_samples (
                sample_time, local_date, gpu_index, gpu_uuid, pid, username,
                process_name, used_memory_mb, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-06-07T10:00:00+08:00", "2026-06-07", 0, "GPU-0", 101, "alice", "python", 1000, "2026-06-07T10:00:00+08:00"),
                ("2026-06-07T10:00:00+08:00", "2026-06-07", 0, "GPU-0", 102, "alice", "python", 2000, "2026-06-07T10:00:00+08:00"),
                ("2026-06-07T10:00:30+08:00", "2026-06-07", 0, "GPU-0", 101, "alice", "python", 4000, "2026-06-07T10:00:30+08:00"),
                ("2026-06-07T10:00:30+08:00", "2026-06-07", 0, "GPU-0", 201, "unknown", "python", 50, "2026-06-07T10:00:30+08:00"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO service_heartbeats (heartbeat_time, status, message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("2026-06-07T10:00:00+08:00", "ok", "heartbeat", "2026-06-07T10:00:00+08:00"),
                ("2026-06-07T10:01:00+08:00", "ok", "heartbeat", "2026-06-07T10:01:00+08:00"),
            ],
        )
