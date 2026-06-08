from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from gpu_monitor.analyzer.report_schema import SUMMARY_SCHEMA_VERSION, report_config_hash
from gpu_monitor.analyzer.session_builder import ActivePoint, build_sessions, merge_sessions
from gpu_monitor.config import Config
from gpu_monitor.storage.database import Database
from gpu_monitor.utils.time_utils import day_bounds, human_duration, isoformat, parse_iso_datetime, parse_local_date


@dataclass(frozen=True)
class DailyAnalyzer:
    database: Database
    config: Config

    def analyze(self, report_date: str | date) -> dict[str, Any]:
        target_date = parse_local_date(report_date) if isinstance(report_date, str) else report_date
        start_dt, end_dt = day_bounds(target_date, self.config.app.timezone)
        start = isoformat(start_dt)
        end = isoformat(end_dt)

        aggregated = self._load_active_points(start, end)
        user_gpu = self._build_user_gpu_entries(aggregated, end_dt)
        heartbeats = self._heartbeat_gaps(start, end)
        errors = self._errors(start, end)
        current_unknown_count = self._unknown_process_count(start, end)

        users = self._users_summary(user_gpu)
        gpus = self._gpus_summary(user_gpu)
        overview = {
            "date": target_date.isoformat(),
            "server_name": self.config.app.server_name,
            "sample_interval_seconds": self.config.collector.sample_interval_seconds,
            "active_memory_threshold_mb": self.config.collector.active_memory_threshold_mb,
            "session_merge_gap_threshold_seconds": self.config.session.merge_gap_threshold_seconds,
            "active_user_count": len(users),
            "used_gpu_count": len(gpus),
            "total_usage_seconds": sum(entry["duration_seconds"] for entry in user_gpu),
            "total_usage_human": human_duration(sum(entry["duration_seconds"] for entry in user_gpu)),
            "heartbeat_gap_count": len(heartbeats),
            "unknown_process_count": current_unknown_count,
            "error_count": len(errors),
        }

        return {
            "summary_schema_version": SUMMARY_SCHEMA_VERSION,
            "report_config_hash": report_config_hash(self.config),
            "report_type": "daily",
            "report_date": target_date.isoformat(),
            "range_start": start,
            "range_end": end,
            "generated_at": isoformat(datetime.now(start_dt.tzinfo)),
            "overview": overview,
            "users": users,
            "gpus": gpus,
            "user_gpu": user_gpu,
            "heartbeat_gaps": heartbeats,
            "errors": errors,
            "notes": [
                f"Only samples with per-user per-GPU memory >= {self.config.collector.active_memory_threshold_mb} MB are counted as active.",
                f"Tasks shorter than {self.config.collector.sample_interval_seconds} seconds may be missed.",
            ],
        }

    def _load_active_points(self, start: str, end: str) -> dict[tuple[str, int], list[ActivePoint]]:
        query = """
            SELECT
                sample_time,
                username,
                gpu_index,
                SUM(used_memory_mb) AS total_used_memory_mb,
                COUNT(*) AS process_count
            FROM gpu_process_samples
            WHERE sample_time >= ? AND sample_time < ?
            GROUP BY sample_time, username, gpu_index
            HAVING total_used_memory_mb >= ?
            ORDER BY username, gpu_index, sample_time
        """
        grouped: dict[tuple[str, int], list[ActivePoint]] = defaultdict(list)
        with self.database.connect() as conn:
            rows = conn.execute(
                query,
                (start, end, self.config.collector.active_memory_threshold_mb),
            ).fetchall()

        for row in rows:
            grouped[(row["username"], int(row["gpu_index"]))].append(
                ActivePoint(
                    sample_time=parse_iso_datetime(row["sample_time"]),
                    memory_mb=float(row["total_used_memory_mb"]),
                    process_count=int(row["process_count"]),
                )
            )
        return grouped

    def _build_user_gpu_entries(
        self,
        grouped: dict[tuple[str, int], list[ActivePoint]],
        range_end: datetime,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for (username, gpu_index), points in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
            raw_sessions = build_sessions(
                points,
                gap_threshold_seconds=self.config.session.gap_threshold_seconds,
                sample_interval_seconds=self.config.collector.sample_interval_seconds,
                range_end=range_end,
            )
            sessions = merge_sessions(raw_sessions, self.config.session.merge_gap_threshold_seconds)
            duration_seconds = sum(session.duration_seconds for session in sessions)
            memory_values = [point.memory_mb for point in points]
            entries.append(
                {
                    "username": username,
                    "display_name": self.config.users.alias.get(username, username),
                    "gpu_index": gpu_index,
                    "active_sample_count": len(points),
                    "process_sample_count": sum(point.process_count for point in points),
                    "duration_seconds": duration_seconds,
                    "duration_human": human_duration(duration_seconds),
                    "avg_memory_mb": round(sum(memory_values) / len(memory_values), 2),
                    "avg_memory_gb": round((sum(memory_values) / len(memory_values)) / 1024, 2),
                    "peak_memory_mb": round(max(memory_values), 2),
                    "peak_memory_gb": round(max(memory_values) / 1024, 2),
                    "sessions": [
                        {
                            "start_time": isoformat(session.start_time),
                            "end_time": isoformat(session.end_time),
                            "duration_seconds": session.duration_seconds,
                            "duration_human": human_duration(session.duration_seconds),
                        }
                        for session in sessions
                    ],
                }
            )
        return entries

    def _users_summary(self, user_gpu: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_user: dict[str, dict[str, Any]] = {}
        for entry in user_gpu:
            username = entry["username"]
            summary = by_user.setdefault(
                username,
                {
                    "username": username,
                    "display_name": entry["display_name"],
                    "gpu_indexes": set(),
                    "duration_seconds": 0,
                    "peak_memory_mb": 0.0,
                    "weighted_memory_sum": 0.0,
                    "active_sample_count": 0,
                },
            )
            summary["gpu_indexes"].add(entry["gpu_index"])
            summary["duration_seconds"] += entry["duration_seconds"]
            summary["peak_memory_mb"] = max(summary["peak_memory_mb"], entry["peak_memory_mb"])
            summary["weighted_memory_sum"] += entry["avg_memory_mb"] * entry["active_sample_count"]
            summary["active_sample_count"] += entry["active_sample_count"]

        users: list[dict[str, Any]] = []
        for summary in by_user.values():
            active_samples = summary["active_sample_count"]
            avg_memory_mb = summary["weighted_memory_sum"] / active_samples if active_samples else 0.0
            users.append(
                {
                    "username": summary["username"],
                    "display_name": summary["display_name"],
                    "gpu_indexes": sorted(summary["gpu_indexes"]),
                    "duration_seconds": summary["duration_seconds"],
                    "duration_human": human_duration(summary["duration_seconds"]),
                    "active_sample_count": active_samples,
                    "avg_memory_mb": round(avg_memory_mb, 2),
                    "avg_memory_gb": round(avg_memory_mb / 1024, 2),
                    "peak_memory_mb": round(summary["peak_memory_mb"], 2),
                    "peak_memory_gb": round(summary["peak_memory_mb"] / 1024, 2),
                }
            )
        return sorted(users, key=lambda item: (-item["duration_seconds"], item["username"]))

    def _gpus_summary(self, user_gpu: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_gpu: dict[int, dict[str, Any]] = {}
        for entry in user_gpu:
            gpu_index = entry["gpu_index"]
            summary = by_gpu.setdefault(
                gpu_index,
                {
                    "gpu_index": gpu_index,
                    "users": set(),
                    "duration_seconds": 0,
                    "peak_memory_mb": 0.0,
                },
            )
            summary["users"].add(entry["username"])
            summary["duration_seconds"] += entry["duration_seconds"]
            summary["peak_memory_mb"] = max(summary["peak_memory_mb"], entry["peak_memory_mb"])

        gpus: list[dict[str, Any]] = []
        for summary in by_gpu.values():
            gpus.append(
                {
                    "gpu_index": summary["gpu_index"],
                    "users": sorted(summary["users"]),
                    "duration_seconds": summary["duration_seconds"],
                    "duration_human": human_duration(summary["duration_seconds"]),
                    "peak_memory_mb": round(summary["peak_memory_mb"], 2),
                    "peak_memory_gb": round(summary["peak_memory_mb"] / 1024, 2),
                }
            )
        return sorted(gpus, key=lambda item: item["gpu_index"])

    def _heartbeat_gaps(self, start: str, end: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT heartbeat_time
                FROM service_heartbeats
                WHERE heartbeat_time >= ? AND heartbeat_time < ?
                ORDER BY heartbeat_time
                """,
                (start, end),
            ).fetchall()

        gaps: list[dict[str, Any]] = []
        previous: datetime | None = None
        for row in rows:
            current = parse_iso_datetime(row["heartbeat_time"])
            if previous is not None:
                gap_seconds = int((current - previous).total_seconds())
                if gap_seconds > self.config.heartbeat.missing_threshold_seconds:
                    gaps.append(
                        {
                            "start_time": isoformat(previous),
                            "end_time": isoformat(current),
                            "gap_seconds": gap_seconds,
                            "gap_human": human_duration(gap_seconds),
                        }
                    )
            previous = current
        return gaps

    def _errors(self, start: str, end: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_time, event_type, severity, message
                FROM error_events
                WHERE event_time >= ? AND event_time < ?
                ORDER BY event_time DESC
                LIMIT 20
                """,
                (start, end),
            ).fetchall()
        return [dict(row) for row in rows]

    def _unknown_process_count(self, start: str, end: str) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM gpu_process_samples
                WHERE sample_time >= ? AND sample_time < ? AND username = 'unknown'
                """,
                (start, end),
            ).fetchone()
        return int(row[0])
