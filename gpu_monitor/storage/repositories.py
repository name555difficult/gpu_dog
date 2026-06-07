from __future__ import annotations

import traceback
from datetime import datetime

from gpu_monitor.collector.models import CollectionResult, GpuDeviceSnapshot, GpuProcessSample
from gpu_monitor.storage.database import Database
from gpu_monitor.utils.time_utils import isoformat, now_local


class MonitorRepository:
    def __init__(self, database: Database, timezone: str):
        self.database = database
        self.timezone = timezone

    def insert_collection(self, result: CollectionResult) -> None:
        with self.database.connect() as conn:
            conn.executemany(
                """
                INSERT INTO gpu_device_snapshots (
                    sample_time, local_date, gpu_index, gpu_uuid, gpu_name,
                    total_memory_mb, gpu_util_percent, memory_util_percent, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_snapshot_row(snapshot) for snapshot in result.snapshots],
            )
            conn.executemany(
                """
                INSERT INTO gpu_process_samples (
                    sample_time, local_date, gpu_index, gpu_uuid, pid,
                    username, process_name, used_memory_mb, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_sample_row(sample) for sample in result.samples],
            )

    def insert_heartbeat(self, status: str = "ok", message: str | None = None) -> None:
        heartbeat_time = isoformat(now_local(self.timezone))
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO service_heartbeats (heartbeat_time, status, message, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (heartbeat_time, status, message, heartbeat_time),
            )

    def insert_error_event(
        self,
        event_type: str,
        message: str,
        severity: str = "ERROR",
        exc: BaseException | None = None,
        event_time: datetime | None = None,
    ) -> None:
        timestamp = isoformat(event_time or now_local(self.timezone))
        tb = "".join(traceback.format_exception(exc)) if exc else None
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO error_events (
                    event_time, event_type, severity, message, traceback, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (timestamp, event_type, severity, message, tb, timestamp),
            )

    def latest_counts(self) -> dict[str, int]:
        with self.database.connect() as conn:
            return {
                "gpu_process_samples": conn.execute("SELECT COUNT(*) FROM gpu_process_samples").fetchone()[0],
                "gpu_device_snapshots": conn.execute("SELECT COUNT(*) FROM gpu_device_snapshots").fetchone()[0],
                "service_heartbeats": conn.execute("SELECT COUNT(*) FROM service_heartbeats").fetchone()[0],
                "error_events": conn.execute("SELECT COUNT(*) FROM error_events").fetchone()[0],
            }


def _snapshot_row(snapshot: GpuDeviceSnapshot) -> tuple:
    return (
        snapshot.sample_time,
        snapshot.local_date,
        snapshot.gpu_index,
        snapshot.gpu_uuid,
        snapshot.gpu_name,
        snapshot.total_memory_mb,
        snapshot.gpu_util_percent,
        snapshot.memory_util_percent,
        snapshot.created_at,
    )


def _sample_row(sample: GpuProcessSample) -> tuple:
    return (
        sample.sample_time,
        sample.local_date,
        sample.gpu_index,
        sample.gpu_uuid,
        sample.pid,
        sample.username,
        sample.process_name,
        sample.used_memory_mb,
        sample.created_at,
    )
