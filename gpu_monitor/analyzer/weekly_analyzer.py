from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from gpu_monitor.analyzer.daily_analyzer import DailyAnalyzer
from gpu_monitor.analyzer.report_schema import SUMMARY_SCHEMA_VERSION
from gpu_monitor.config import Config
from gpu_monitor.storage.database import Database
from gpu_monitor.utils.time_utils import date_range, human_duration, isoformat, now_local, parse_local_date, week_bounds


@dataclass(frozen=True)
class WeeklyAnalyzer:
    database: Database
    config: Config

    def analyze(self, week_date: str | date, daily_summaries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        target = parse_local_date(week_date) if isinstance(week_date, str) else week_date
        week_start, week_end, start_dt, end_dt = week_bounds(target, self.config.app.timezone)
        today = now_local(self.config.app.timezone).date()
        days = [day for day in date_range(week_start, 7) if day <= today]

        if daily_summaries is None:
            daily = DailyAnalyzer(self.database, self.config)
            daily_summaries = [daily.analyze(day) for day in days]

        users = self._users_summary(daily_summaries)
        gpus = self._gpus_summary(daily_summaries)
        missing_dates = [
            summary["report_date"]
            for summary in daily_summaries
            if summary["overview"]["active_user_count"] == 0
            and summary["overview"]["used_gpu_count"] == 0
            and summary["overview"]["error_count"] == 0
        ]
        total_usage_seconds = sum(summary["overview"]["total_usage_seconds"] for summary in daily_summaries)

        return {
            "summary_schema_version": SUMMARY_SCHEMA_VERSION,
            "report_type": "weekly",
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "range_start": isoformat(start_dt),
            "range_end": isoformat(end_dt),
            "generated_at": isoformat(now_local(self.config.app.timezone)),
            "overview": {
                "server_name": self.config.app.server_name,
                "session_merge_gap_threshold_seconds": self.config.session.merge_gap_threshold_seconds,
                "active_user_count": len(users),
                "used_gpu_count": len(gpus),
                "total_usage_seconds": total_usage_seconds,
                "total_usage_human": human_duration(total_usage_seconds),
                "heartbeat_gap_count": sum(len(summary["heartbeat_gaps"]) for summary in daily_summaries),
                "error_count": sum(summary["overview"]["error_count"] for summary in daily_summaries),
                "missing_or_empty_dates": missing_dates,
                "future_dates": [day.isoformat() for day in date_range(week_start, 7) if day > today],
            },
            "users": users,
            "gpus": gpus,
            "daily": [
                {
                    "date": summary["report_date"],
                    "active_user_count": summary["overview"]["active_user_count"],
                    "used_gpu_count": summary["overview"]["used_gpu_count"],
                    "total_usage_seconds": summary["overview"]["total_usage_seconds"],
                    "total_usage_human": summary["overview"]["total_usage_human"],
                    "heartbeat_gap_count": summary["overview"]["heartbeat_gap_count"],
                    "error_count": summary["overview"]["error_count"],
                }
                for summary in daily_summaries
            ],
        }

    def _users_summary(self, daily_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_user: dict[str, dict[str, Any]] = {}
        for summary in daily_summaries:
            for user in summary["users"]:
                record = by_user.setdefault(
                    user["username"],
                    {
                        "username": user["username"],
                        "display_name": user["display_name"],
                        "gpu_indexes": set(),
                        "duration_seconds": 0,
                        "peak_memory_mb": 0.0,
                        "weighted_memory_sum": 0.0,
                        "active_days": 0,
                    },
                )
                record["gpu_indexes"].update(user["gpu_indexes"])
                record["duration_seconds"] += user["duration_seconds"]
                record["peak_memory_mb"] = max(record["peak_memory_mb"], user["peak_memory_mb"])
                record["weighted_memory_sum"] += user["avg_memory_mb"]
                record["active_days"] += 1

        result: list[dict[str, Any]] = []
        for record in by_user.values():
            active_days = record["active_days"]
            avg_memory_mb = record["weighted_memory_sum"] / active_days if active_days else 0.0
            result.append(
                {
                    "username": record["username"],
                    "display_name": record["display_name"],
                    "gpu_indexes": sorted(record["gpu_indexes"]),
                    "duration_seconds": record["duration_seconds"],
                    "duration_human": human_duration(record["duration_seconds"]),
                    "daily_avg_usage_seconds": int(record["duration_seconds"] / 7),
                    "daily_avg_usage_human": human_duration(int(record["duration_seconds"] / 7)),
                    "avg_memory_mb": round(avg_memory_mb, 2),
                    "avg_memory_gb": round(avg_memory_mb / 1024, 2),
                    "peak_memory_mb": round(record["peak_memory_mb"], 2),
                    "peak_memory_gb": round(record["peak_memory_mb"] / 1024, 2),
                    "active_days": active_days,
                }
            )
        return sorted(result, key=lambda item: (-item["duration_seconds"], item["username"]))

    def _gpus_summary(self, daily_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_gpu: dict[int, dict[str, Any]] = {}
        for summary in daily_summaries:
            for gpu in summary["gpus"]:
                record = by_gpu.setdefault(
                    gpu["gpu_index"],
                    {
                        "gpu_index": gpu["gpu_index"],
                        "users": set(),
                        "duration_seconds": 0,
                        "peak_memory_mb": 0.0,
                        "active_days": 0,
                    },
                )
                record["users"].update(gpu["users"])
                record["duration_seconds"] += gpu["duration_seconds"]
                record["peak_memory_mb"] = max(record["peak_memory_mb"], gpu["peak_memory_mb"])
                record["active_days"] += 1

        result: list[dict[str, Any]] = []
        for record in by_gpu.values():
            result.append(
                {
                    "gpu_index": record["gpu_index"],
                    "users": sorted(record["users"]),
                    "duration_seconds": record["duration_seconds"],
                    "duration_human": human_duration(record["duration_seconds"]),
                    "peak_memory_mb": round(record["peak_memory_mb"], 2),
                    "peak_memory_gb": round(record["peak_memory_mb"] / 1024, 2),
                    "active_days": record["active_days"],
                }
            )
        return sorted(result, key=lambda item: item["gpu_index"])
