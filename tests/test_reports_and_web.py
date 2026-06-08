from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from gpu_monitor.analyzer.daily_analyzer import DailyAnalyzer
from gpu_monitor.analyzer.report_schema import SUMMARY_SCHEMA_VERSION
from gpu_monitor.analyzer.weekly_analyzer import WeeklyAnalyzer
from gpu_monitor.reports.markdown_export import daily_to_markdown, weekly_to_markdown
from gpu_monitor.reports.json_cache import ReportCache
from gpu_monitor.utils.zoneinfo_compat import ZoneInfo
from gpu_monitor.web.dashboard import current_snapshot, day_summary, health_status, today_summary, week_summary
from tests.helpers import TempProject, seed_sample_data


class ReportsAndWebTest(unittest.TestCase):
    def test_report_cache_and_dashboard_helpers(self) -> None:
        with TempProject() as (config, database):
            seed_sample_data(database)
            cache = ReportCache(database, config)
            daily = cache.generate_daily("2026-06-07", force=True)
            weekly = cache.generate_weekly("2026-06-07", force=True)
            current = current_snapshot(database, config)
            health = health_status(database, config)
            day = day_summary(database, config, "2026-06-07")
            week = week_summary(database, config, "2026-06-07")

        self.assertEqual(daily["overview"]["total_usage_seconds"], 60)
        self.assertEqual(weekly["overview"]["active_user_count"], 1)
        self.assertEqual(current["collector_status"], "ok")
        self.assertEqual(current["gpus"][0]["used_memory_mb"], 4050)
        self.assertEqual(health["status"], "ok")
        self.assertIn("storage", health)
        self.assertEqual(day["report_type"], "daily")
        self.assertEqual(week["report_type"], "weekly")

    def test_report_cache_regenerates_legacy_daily_summary(self) -> None:
        with TempProject() as (config, database):
            seed_sample_data(database)
            _seed_full_day_snapshot_coverage(database, "2026-06-07")
            cache = ReportCache(database, config)
            daily = cache.generate_daily("2026-06-07", force=True)
            record = cache._daily_record("2026-06-07")
            path = Path(record["json_path"])
            legacy = dict(daily)
            legacy["overview"] = dict(legacy["overview"])
            legacy.pop("summary_schema_version", None)
            legacy["overview"].pop("session_merge_gap_threshold_seconds", None)
            path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
            refreshed = dict(daily)
            refreshed["generated_at"] = "regenerated"

            with patch.object(DailyAnalyzer, "analyze", return_value=refreshed) as analyze:
                result = cache.generate_daily("2026-06-07")

        self.assertEqual(result["generated_at"], "regenerated")
        self.assertEqual(result["summary_schema_version"], SUMMARY_SCHEMA_VERSION)
        analyze.assert_called_once()

    def test_report_cache_preserves_legacy_daily_when_raw_is_unavailable(self) -> None:
        with TempProject() as (config, database):
            cache = ReportCache(database, config)
            path = Path(config.reports.cache_dir) / "daily" / "2026-06-01.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            legacy = {
                "report_type": "daily",
                "report_date": "2026-06-01",
                "overview": {
                    "total_usage_seconds": 3600,
                    "total_usage_human": "1h 0m",
                    "active_user_count": 1,
                    "used_gpu_count": 1,
                    "error_count": 0,
                    "heartbeat_gap_count": 0,
                },
                "users": [{"username": "alice"}],
                "gpus": [],
                "user_gpu": [],
                "heartbeat_gaps": [],
                "errors": [],
            }
            path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
            with database.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO daily_reports (
                        report_date, status, generated_at, json_path, content_hash,
                        created_at, updated_at
                    )
                    VALUES (?, 'generated', ?, ?, ?, ?, ?)
                    """,
                    ("2026-06-01", "old", str(path), "oldhash", "old", "old"),
                )

            with patch.object(DailyAnalyzer, "analyze") as analyze:
                result = cache.generate_daily("2026-06-01")

        self.assertEqual(result["overview"]["total_usage_seconds"], 3600)
        analyze.assert_not_called()

    def test_report_cache_regenerates_when_merge_threshold_changes(self) -> None:
        with TempProject() as (config, database):
            seed_sample_data(database)
            _seed_full_day_snapshot_coverage(database, "2026-06-07")
            cache = ReportCache(database, config)
            daily = cache.generate_daily("2026-06-07", force=True)
            changed_config = replace(config, session=replace(config.session, merge_gap_threshold_seconds=1800))
            refreshed = dict(daily)
            refreshed["overview"] = dict(daily["overview"])
            refreshed["overview"]["session_merge_gap_threshold_seconds"] = 1800

            with patch.object(DailyAnalyzer, "analyze", return_value=refreshed) as analyze:
                result = ReportCache(database, changed_config).generate_daily("2026-06-07")

        self.assertEqual(result["overview"]["session_merge_gap_threshold_seconds"], 1800)
        analyze.assert_called_once()

    def test_weekly_user_average_memory_is_sample_weighted(self) -> None:
        with TempProject() as (config, database):
            daily_summaries = [
                _daily_stub("2026-06-08", avg_memory_mb=1000, active_sample_count=10),
                _daily_stub("2026-06-09", avg_memory_mb=10000, active_sample_count=1),
            ]
            weekly = WeeklyAnalyzer(database, config).analyze("2026-06-08", daily_summaries=daily_summaries)

        user = weekly["users"][0]
        self.assertEqual(user["active_sample_count"], 11)
        self.assertEqual(user["avg_memory_mb"], 1818.18)

    def test_markdown_exports_include_report_tables(self) -> None:
        with TempProject() as (config, database):
            seed_sample_data(database)
            daily = day_summary(database, config, "2026-06-07")
            weekly = week_summary(database, config, "2026-06-07")

        daily_markdown = daily_to_markdown(daily)
        weekly_markdown = weekly_to_markdown(weekly)

        self.assertIn("# GPU Daily Report - 2026-06-07", daily_markdown)
        self.assertIn("| User | GPU | Sessions | Duration | Avg Memory | Peak Memory |", daily_markdown)
        self.assertIn("Alice", daily_markdown)
        self.assertNotIn("## Issues", daily_markdown)
        self.assertIn("# GPU Weekly Report - 2026-06-01 to 2026-06-07", weekly_markdown)
        self.assertIn("| Date | Users | GPUs | Usage | Heartbeat Gaps | Errors |", weekly_markdown)

    def test_today_summary_uses_latest_sample_cache(self) -> None:
        fake_now = datetime(2026, 6, 7, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with TempProject() as (config, database):
            seed_sample_data(database)
            with patch("gpu_monitor.web.dashboard.now_local", return_value=fake_now), patch.object(
                DailyAnalyzer,
                "analyze",
                return_value={"report_type": "daily", "report_date": "2026-06-07"},
            ) as analyze:
                first = today_summary(database, config)
                second = today_summary(database, config)

        self.assertEqual(first, second)
        analyze.assert_called_once()

    def test_current_week_summary_uses_latest_sample_cache(self) -> None:
        fake_now = datetime(2026, 6, 8, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with TempProject() as (config, database):
            seed_sample_data(database)
            with patch("gpu_monitor.web.dashboard.now_local", return_value=fake_now), patch(
                "gpu_monitor.web.dashboard.today_summary",
                return_value={
                    "report_type": "daily",
                    "report_date": "2026-06-08",
                    "overview": {"active_user_count": 0, "used_gpu_count": 0, "error_count": 0, "total_usage_seconds": 0},
                    "users": [],
                    "gpus": [],
                    "heartbeat_gaps": [],
                },
            ), patch.object(
                WeeklyAnalyzer,
                "analyze",
                return_value={"report_type": "weekly", "week_start": "2026-06-08"},
            ) as analyze:
                first = week_summary(database, config, "2026-06-08")
                second = week_summary(database, config, "2026-06-08")

        self.assertEqual(first, second)
        analyze.assert_called_once()


def _daily_stub(report_date: str, avg_memory_mb: float, active_sample_count: int) -> dict:
    return {
        "report_type": "daily",
        "report_date": report_date,
        "overview": {
            "active_user_count": 1,
            "used_gpu_count": 1,
            "error_count": 0,
            "total_usage_seconds": 60,
            "total_usage_human": "1m 0s",
            "heartbeat_gap_count": 0,
        },
        "users": [
            {
                "username": "alice",
                "display_name": "Alice",
                "gpu_indexes": [0],
                "duration_seconds": 60,
                "duration_human": "1m 0s",
                "avg_memory_mb": avg_memory_mb,
                "avg_memory_gb": round(avg_memory_mb / 1024, 2),
                "peak_memory_mb": avg_memory_mb,
                "peak_memory_gb": round(avg_memory_mb / 1024, 2),
                "active_sample_count": active_sample_count,
            }
        ],
        "gpus": [
            {
                "gpu_index": 0,
                "users": ["alice"],
                "duration_seconds": 60,
                "duration_human": "1m 0s",
                "peak_memory_mb": avg_memory_mb,
                "peak_memory_gb": round(avg_memory_mb / 1024, 2),
            }
        ],
        "heartbeat_gaps": [],
    }


def _seed_full_day_snapshot_coverage(database, report_date: str) -> None:
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
                (f"{report_date}T00:00:00+08:00", report_date, 0, "GPU-0", "Test GPU", 24000, 0, 0, f"{report_date}T00:00:00+08:00"),
                (f"{report_date}T23:59:30+08:00", report_date, 0, "GPU-0", "Test GPU", 24000, 0, 0, f"{report_date}T23:59:30+08:00"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
