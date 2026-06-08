from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from gpu_monitor.config import Config
from gpu_monitor.storage.database import Database
from gpu_monitor.utils.time_utils import isoformat, now_local

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupManager:
    database: Database
    config: Config

    def run(self) -> dict[str, Any]:
        now = now_local(self.config.app.timezone)
        cleanup = self.config.storage.cleanup
        cutoffs = {
            "raw": isoformat(now - timedelta(days=cleanup.raw_retention_days)),
            "snapshots": isoformat(now - timedelta(days=cleanup.gpu_snapshot_retention_days)),
            "errors": isoformat(now - timedelta(days=cleanup.error_log_retention_days)),
            "heartbeats": isoformat(now - timedelta(days=cleanup.heartbeat_retention_days)),
            "daily_date": (now.date() - timedelta(days=cleanup.daily_cache_retention_days)).isoformat(),
            "weekly_end": (now.date() - timedelta(weeks=cleanup.weekly_cache_retention_weeks)).isoformat(),
        }

        result: dict[str, Any] = {}
        with self.database.connect() as conn:
            result["gpu_process_samples"] = conn.execute(
                "DELETE FROM gpu_process_samples WHERE sample_time < ?",
                (cutoffs["raw"],),
            ).rowcount
            result["gpu_device_snapshots"] = conn.execute(
                "DELETE FROM gpu_device_snapshots WHERE sample_time < ?",
                (cutoffs["snapshots"],),
            ).rowcount
            result["service_heartbeats"] = conn.execute(
                "DELETE FROM service_heartbeats WHERE heartbeat_time < ?",
                (cutoffs["heartbeats"],),
            ).rowcount
            result["error_events"] = conn.execute(
                "DELETE FROM error_events WHERE event_time < ?",
                (cutoffs["errors"],),
            ).rowcount

            daily_rows = conn.execute(
                "SELECT id, json_path FROM daily_reports WHERE report_date < ?",
                (cutoffs["daily_date"],),
            ).fetchall()
            weekly_rows = conn.execute(
                "SELECT id, json_path FROM weekly_reports WHERE week_end < ?",
                (cutoffs["weekly_end"],),
            ).fetchall()

            result["daily_report_files"] = self._delete_files([row["json_path"] for row in daily_rows])
            result["weekly_report_files"] = self._delete_files([row["json_path"] for row in weekly_rows])

            if daily_rows:
                conn.executemany("DELETE FROM daily_reports WHERE id = ?", [(row["id"],) for row in daily_rows])
            if weekly_rows:
                conn.executemany("DELETE FROM weekly_reports WHERE id = ?", [(row["id"],) for row in weekly_rows])
            result["daily_reports"] = len(daily_rows)
            result["weekly_reports"] = len(weekly_rows)

        storage_stats = self.database.storage_stats()
        result["storage"] = storage_stats
        if (
            cleanup.compact_after_cleanup
            and storage_stats["freelist_ratio"] >= cleanup.compact_min_freelist_ratio
        ):
            result["compact"] = self.database.compact()
        else:
            result["compact"] = None

        logger.info("Cleanup completed: %s", result)
        return result

    def _delete_files(self, paths: list[str | None]) -> int:
        deleted = 0
        for raw_path in paths:
            if not raw_path:
                continue
            path = Path(raw_path)
            try:
                if path.exists() and path.is_file():
                    path.unlink()
                    deleted += 1
            except OSError as exc:
                logger.warning("Unable to delete report cache %s: %s", path, exc)
        return deleted
