from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta

from gpu_monitor.cleanup.cleanup_manager import CleanupManager
from gpu_monitor.config import Config
from gpu_monitor.reports.json_cache import ReportCache
from gpu_monitor.storage.database import Database
from gpu_monitor.utils.time_utils import now_local, parse_local_date

logger = logging.getLogger(__name__)


@dataclass
class SimpleScheduler:
    database: Database
    config: Config
    _last_daily: date | None = field(default=None, init=False)
    _last_weekly: date | None = field(default=None, init=False)
    _last_cleanup: date | None = field(default=None, init=False)

    def run_startup_compensation(self) -> None:
        today = now_local(self.config.app.timezone).date()
        yesterday = today - timedelta(days=1)
        cache = ReportCache(self.database, self.config)
        try:
            cache.generate_daily(yesterday)
            logger.info("Startup compensation checked daily cache for %s", yesterday)
        except Exception:
            logger.exception("Startup daily compensation failed")

        if today.weekday() == 0:
            previous_week_day = today - timedelta(days=7)
        else:
            previous_week_day = today - timedelta(days=today.weekday() + 1)
        try:
            cache.generate_weekly(previous_week_day)
            logger.info("Startup compensation checked weekly cache for %s", previous_week_day)
        except Exception:
            logger.exception("Startup weekly compensation failed")

    def run_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            self.run_due_jobs()
            stop_event.wait(30)

    def run_due_jobs(self) -> None:
        now = now_local(self.config.app.timezone)
        today = now.date()
        hhmm = now.strftime("%H:%M")

        if hhmm >= self.config.reports.daily_generate_time and self._last_daily != today:
            target = today - timedelta(days=1)
            self._safe_daily(target)
            self._last_daily = today

        weekly_day = self.config.reports.weekly_generate_day.lower()
        is_weekly_day = weekly_day == "monday" and today.weekday() == 0
        if is_weekly_day and hhmm >= self.config.reports.weekly_generate_time and self._last_weekly != today:
            self._safe_weekly(today - timedelta(days=7))
            self._last_weekly = today

        if hhmm >= "01:00" and self._last_cleanup != today:
            self._safe_cleanup()
            self._last_cleanup = today

    def _safe_daily(self, target: date) -> None:
        try:
            ReportCache(self.database, self.config).generate_daily(target)
            logger.info("Generated daily cache for %s", target)
        except Exception:
            logger.exception("Daily cache generation failed for %s", target)

    def _safe_weekly(self, target: date) -> None:
        try:
            ReportCache(self.database, self.config).generate_weekly(target)
            logger.info("Generated weekly cache for %s", target)
        except Exception:
            logger.exception("Weekly cache generation failed for %s", target)

    def _safe_cleanup(self) -> None:
        try:
            CleanupManager(self.database, self.config).run()
        except Exception:
            logger.exception("Cleanup failed")


def parse_job_date(value: str | None, timezone: str) -> date:
    if value:
        return parse_local_date(value)
    return now_local(timezone).date()
