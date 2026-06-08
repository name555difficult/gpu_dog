from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from gpu_monitor.analyzer.daily_analyzer import DailyAnalyzer
from gpu_monitor.analyzer.weekly_analyzer import WeeklyAnalyzer
from gpu_monitor.config import Config
from gpu_monitor.storage.database import Database
from gpu_monitor.utils.time_utils import isoformat, now_local, parse_local_date, week_bounds


@dataclass(frozen=True)
class ReportCache:
    database: Database
    config: Config

    def generate_daily(self, report_date: str | date, force: bool = False) -> dict[str, Any]:
        target = parse_local_date(report_date) if isinstance(report_date, str) else report_date
        existing = self._daily_record(target.isoformat())
        if existing and existing["status"] == "generated" and existing["json_path"] and not force:
            path = Path(existing["json_path"])
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))

        summary = DailyAnalyzer(self.database, self.config).analyze(target)
        path = self._daily_path(target)
        self._write_json(path, summary)
        self._upsert_daily(target.isoformat(), path, _file_hash(path), None)
        return summary

    def generate_weekly(self, week_date: str | date, force: bool = False) -> dict[str, Any]:
        target = parse_local_date(week_date) if isinstance(week_date, str) else week_date
        week_start, week_end, _, _ = week_bounds(target, self.config.app.timezone)
        existing = self._weekly_record(week_start.isoformat(), week_end.isoformat())
        if existing and existing["status"] == "generated" and existing["json_path"] and not force:
            path = Path(existing["json_path"])
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))

        today = now_local(self.config.app.timezone).date()
        daily_summaries = [self.generate_daily(day, force=force) for day in _days(week_start, 7) if day <= today]
        summary = WeeklyAnalyzer(self.database, self.config).analyze(week_start, daily_summaries=daily_summaries)
        path = self._weekly_path(week_start, week_end)
        self._write_json(path, summary)
        self._upsert_weekly(week_start.isoformat(), week_end.isoformat(), path, _file_hash(path), None)
        return summary

    def _daily_path(self, report_date: date) -> Path:
        return Path(self.config.reports.cache_dir) / "daily" / f"{report_date.isoformat()}.json"

    def _weekly_path(self, week_start: date, week_end: date) -> Path:
        return Path(self.config.reports.cache_dir) / "weekly" / f"{week_start.isoformat()}_{week_end.isoformat()}.json"

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _daily_record(self, report_date: str):
        with self.database.connect() as conn:
            return conn.execute("SELECT * FROM daily_reports WHERE report_date = ?", (report_date,)).fetchone()

    def _weekly_record(self, week_start: str, week_end: str):
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT * FROM weekly_reports WHERE week_start = ? AND week_end = ?",
                (week_start, week_end),
            ).fetchone()

    def _upsert_daily(self, report_date: str, path: Path, content_hash: str, error_message: str | None) -> None:
        timestamp = isoformat(now_local(self.config.app.timezone))
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_reports (
                    report_date, status, generated_at, json_path, content_hash,
                    error_message, created_at, updated_at
                )
                VALUES (?, 'generated', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    status = excluded.status,
                    generated_at = excluded.generated_at,
                    json_path = excluded.json_path,
                    content_hash = excluded.content_hash,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (report_date, timestamp, str(path), content_hash, error_message, timestamp, timestamp),
            )

    def _upsert_weekly(
        self,
        week_start: str,
        week_end: str,
        path: Path,
        content_hash: str,
        error_message: str | None,
    ) -> None:
        timestamp = isoformat(now_local(self.config.app.timezone))
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO weekly_reports (
                    week_start, week_end, status, generated_at, json_path, content_hash,
                    error_message, created_at, updated_at
                )
                VALUES (?, ?, 'generated', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(week_start, week_end) DO UPDATE SET
                    status = excluded.status,
                    generated_at = excluded.generated_at,
                    json_path = excluded.json_path,
                    content_hash = excluded.content_hash,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (week_start, week_end, timestamp, str(path), content_hash, error_message, timestamp, timestamp),
            )


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _days(start: date, count: int) -> list[date]:
    from datetime import timedelta

    return [start + timedelta(days=offset) for offset in range(count)]
