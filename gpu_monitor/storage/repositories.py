from __future__ import annotations

import traceback
import logging
from datetime import datetime
from pathlib import Path

from gpu_monitor.collector.models import CollectionResult, GpuDeviceSnapshot, GpuProcessSample
from gpu_monitor.storage.database import Database
from gpu_monitor.utils.time_utils import isoformat, now_local

logger = logging.getLogger(__name__)
UNKNOWN_REPAIR_WINDOW_SECONDS = 600
MISSING_PROCESS_NAMES = ("", "[No data]")


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

    def repair_unknown_users(self, dry_run: bool = False) -> list[dict[str, object]]:
        repairs: list[dict[str, object]] = []
        affected_dates: set[str] = set()
        with self.database.connect() as conn:
            unknown_rows = conn.execute(
                """
                SELECT id, sample_time, local_date, gpu_index, pid, process_name, used_memory_mb
                FROM gpu_process_samples
                WHERE username = 'unknown'
                ORDER BY sample_time
                """
            ).fetchall()
            for row in unknown_rows:
                candidates = conn.execute(
                    """
                    SELECT
                        username,
                        process_name,
                        sample_time,
                        ABS((julianday(sample_time) - julianday(?)) * 86400.0) AS gap_seconds
                    FROM gpu_process_samples
                    WHERE pid = ?
                      AND gpu_index = ?
                      AND username != 'unknown'
                      AND ABS((julianday(sample_time) - julianday(?)) * 86400.0) <= ?
                    ORDER BY gap_seconds, sample_time
                    """,
                    (
                        row["sample_time"],
                        row["pid"],
                        row["gpu_index"],
                        row["sample_time"],
                        UNKNOWN_REPAIR_WINDOW_SECONDS,
                    ),
                ).fetchall()
                candidates = [
                    candidate
                    for candidate in candidates
                    if _process_names_compatible(row["process_name"], candidate["process_name"])
                ]
                candidate_users = {candidate["username"] for candidate in candidates}
                if len(candidate_users) != 1:
                    continue
                known = candidates[0]
                process_name = row["process_name"]
                if _missing_process_name(process_name) and known["process_name"]:
                    process_name = known["process_name"]
                repairs.append(
                    {
                        "id": row["id"],
                        "sample_time": row["sample_time"],
                        "gpu_index": row["gpu_index"],
                        "pid": row["pid"],
                        "old_username": "unknown",
                        "new_username": known["username"],
                        "old_process_name": row["process_name"],
                        "new_process_name": process_name,
                        "reference_sample_time": known["sample_time"],
                        "reference_gap_seconds": int(float(known["gap_seconds"])),
                        "used_memory_mb": row["used_memory_mb"],
                    }
                )
                if not dry_run:
                    affected_dates.add(row["local_date"])
                    conn.execute(
                        """
                        UPDATE gpu_process_samples
                        SET username = ?, process_name = ?
                        WHERE id = ?
                        """,
                        (known["username"], process_name, row["id"]),
                    )
            if affected_dates and not dry_run:
                self._invalidate_report_caches(conn, affected_dates)
        return repairs

    @staticmethod
    def _invalidate_report_caches(conn, affected_dates: set[str]) -> None:
        daily_rows = conn.execute(
            f"""
            SELECT id, json_path
            FROM daily_reports
            WHERE report_date IN ({",".join("?" for _ in affected_dates)})
            """,
            tuple(sorted(affected_dates)),
        ).fetchall()
        weekly_rows = conn.execute(
            """
            SELECT id, json_path, week_start, week_end
            FROM weekly_reports
            """
        ).fetchall()
        weekly_rows = [
            row
            for row in weekly_rows
            if any(row["week_start"] <= affected_date <= row["week_end"] for affected_date in affected_dates)
        ]

        _delete_report_files(row["json_path"] for row in daily_rows)
        _delete_report_files(row["json_path"] for row in weekly_rows)

        if daily_rows:
            conn.executemany("DELETE FROM daily_reports WHERE id = ?", [(row["id"],) for row in daily_rows])
        if weekly_rows:
            conn.executemany("DELETE FROM weekly_reports WHERE id = ?", [(row["id"],) for row in weekly_rows])


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


def _missing_process_name(value: str | None) -> bool:
    return value is None or value in MISSING_PROCESS_NAMES


def _process_names_compatible(unknown_name: str | None, known_name: str | None) -> bool:
    if _missing_process_name(unknown_name) or _missing_process_name(known_name):
        return True
    return unknown_name == known_name


def _delete_report_files(paths) -> None:
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path)
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError as exc:
            logger.warning("Unable to delete invalidated report cache %s: %s", path, exc)
