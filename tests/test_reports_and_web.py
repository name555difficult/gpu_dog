from __future__ import annotations

import unittest

from gpu_monitor.reports.json_cache import ReportCache
from gpu_monitor.web.dashboard import current_snapshot, day_summary, health_status, week_summary
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
        self.assertEqual(day["report_type"], "daily")
        self.assertEqual(week["report_type"], "weekly")


if __name__ == "__main__":
    unittest.main()
