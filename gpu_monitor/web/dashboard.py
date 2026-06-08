from __future__ import annotations

import json
import logging
import mimetypes
import threading
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from gpu_monitor.analyzer.report_schema import report_config_hash
from gpu_monitor.analyzer.daily_analyzer import DailyAnalyzer
from gpu_monitor.analyzer.weekly_analyzer import WeeklyAnalyzer
from gpu_monitor.config import Config
from gpu_monitor.reports.markdown_export import daily_to_markdown, weekly_to_markdown
from gpu_monitor.reports.json_cache import ReportCache
from gpu_monitor.storage.database import Database
from gpu_monitor.utils.time_utils import date_range, isoformat, now_local, parse_local_date, week_bounds

logger = logging.getLogger(__name__)
_SUMMARY_CACHE = None


def run_dashboard_server(config: Config, database: Database, stop_event: threading.Event) -> None:
    server = build_server(config, database)
    server.timeout = 1
    logger.info("Dashboard listening on http://%s:%s", config.web.host, config.web.port)
    try:
        while not stop_event.is_set():
            server.handle_request()
    finally:
        server.server_close()
        logger.info("Dashboard server stopped")


def build_server(config: Config, database: Database) -> ThreadingHTTPServer:
    class Handler(DashboardRequestHandler):
        app_config = config
        app_database = database

    return ThreadingHTTPServer((config.web.host, config.web.port), Handler)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    app_config: Config
    app_database: Database

    def do_GET(self) -> None:
        try:
            self._handle_get()
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logger.exception("Dashboard request failed")
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug("dashboard: " + fmt, *args)

    def _handle_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self._send_html(_html_shell("today", None, self.app_config))
            return
        if path == "/health":
            self._send_html(_html_shell("health", None, self.app_config))
            return
        if path.startswith("/day/"):
            value = path.removeprefix("/day/").strip("/")
            parse_local_date(value)
            self._send_html(_html_shell("day", value, self.app_config))
            return
        if path.startswith("/week/"):
            value = path.removeprefix("/week/").strip("/")
            parse_local_date(value)
            self._send_html(_html_shell("week", value, self.app_config))
            return
        if path.startswith("/static/"):
            self._send_static(path.removeprefix("/static/"))
            return

        if path == "/api/current":
            self._send_json(current_snapshot(self.app_database, self.app_config))
            return
        if path == "/api/today":
            self._send_json(today_summary(self.app_database, self.app_config))
            return
        if path == "/api/day":
            day = _first_query_value(query, "date") or now_local(self.app_config.app.timezone).date().isoformat()
            self._send_json(day_summary(self.app_database, self.app_config, day))
            return
        if path == "/api/week":
            value = (
                _first_query_value(query, "date")
                or _first_query_value(query, "start")
                or now_local(self.app_config.app.timezone).date().isoformat()
            )
            self._send_json(week_summary(self.app_database, self.app_config, value))
            return
        if path == "/api/health":
            self._send_json(health_status(self.app_database, self.app_config))
            return
        if path == "/export/day":
            day = _first_query_value(query, "date") or now_local(self.app_config.app.timezone).date().isoformat()
            summary = day_summary(self.app_database, self.app_config, day)
            self._send_markdown(daily_to_markdown(summary), f"gpu-monitor-day-{summary['report_date']}.md")
            return
        if path == "/export/week":
            value = (
                _first_query_value(query, "date")
                or _first_query_value(query, "start")
                or now_local(self.app_config.app.timezone).date().isoformat()
            )
            summary = week_summary(self.app_database, self.app_config, value)
            filename = f"gpu-monitor-week-{summary['week_start']}_{summary['week_end']}.md"
            self._send_markdown(weekly_to_markdown(summary), filename)
            return

        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_markdown(self, body: str, filename: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_static(self, name: str) -> None:
        root = Path(__file__).with_name("static")
        target = (root / name).resolve()
        if root.resolve() not in target.parents or not target.exists() or not target.is_file():
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        payload = target.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def current_snapshot(database: Database, config: Config) -> dict[str, Any]:
    with database.connect() as conn:
        sample_row = conn.execute("SELECT MAX(sample_time) FROM gpu_device_snapshots").fetchone()
        sample_time = sample_row[0] if sample_row else None
        snapshots = []
        processes = []
        if sample_time:
            snapshots = conn.execute(
                """
                SELECT sample_time, gpu_index, gpu_uuid, gpu_name, total_memory_mb,
                       gpu_util_percent, memory_util_percent
                FROM gpu_device_snapshots
                WHERE sample_time = ?
                ORDER BY gpu_index
                """,
                (sample_time,),
            ).fetchall()
            processes = conn.execute(
                """
                SELECT gpu_index, gpu_uuid, pid, username, process_name, used_memory_mb
                FROM gpu_process_samples
                WHERE sample_time = ?
                ORDER BY gpu_index, username, pid
                """,
                (sample_time,),
            ).fetchall()
        error = conn.execute(
            """
            SELECT event_time, event_type, severity, message
            FROM error_events
            ORDER BY event_time DESC
            LIMIT 1
            """
        ).fetchone()

    process_by_gpu: dict[int, list[dict[str, Any]]] = {}
    for row in processes:
        process_by_gpu.setdefault(int(row["gpu_index"]), []).append(
            {
                "pid": int(row["pid"]),
                "username": row["username"],
                "display_name": config.users.alias.get(row["username"], row["username"]),
                "process_name": row["process_name"],
                "used_memory_mb": float(row["used_memory_mb"]),
                "used_memory_gb": round(float(row["used_memory_mb"]) / 1024, 2),
            }
        )

    gpus = []
    for row in snapshots:
        gpu_processes = process_by_gpu.get(int(row["gpu_index"]), [])
        used_memory_mb = sum(process["used_memory_mb"] for process in gpu_processes)
        gpus.append(
            {
                "gpu_index": int(row["gpu_index"]),
                "gpu_uuid": row["gpu_uuid"],
                "gpu_name": row["gpu_name"],
                "total_memory_mb": row["total_memory_mb"],
                "total_memory_gb": round(float(row["total_memory_mb"] or 0) / 1024, 2),
                "used_memory_mb": round(used_memory_mb, 2),
                "used_memory_gb": round(used_memory_mb / 1024, 2),
                "gpu_util_percent": row["gpu_util_percent"],
                "memory_util_percent": row["memory_util_percent"],
                "processes": gpu_processes,
            }
        )

    users: dict[str, dict[str, Any]] = {}
    for row in processes:
        username = row["username"]
        record = users.setdefault(
            username,
            {
                "username": username,
                "display_name": config.users.alias.get(username, username),
                "gpu_indexes": set(),
                "process_count": 0,
                "used_memory_mb": 0.0,
            },
        )
        record["gpu_indexes"].add(int(row["gpu_index"]))
        record["process_count"] += 1
        record["used_memory_mb"] += float(row["used_memory_mb"])

    user_list = []
    for record in users.values():
        user_list.append(
            {
                "username": record["username"],
                "display_name": record["display_name"],
                "gpu_indexes": sorted(record["gpu_indexes"]),
                "process_count": record["process_count"],
                "used_memory_mb": round(record["used_memory_mb"], 2),
                "used_memory_gb": round(record["used_memory_mb"] / 1024, 2),
            }
        )

    return {
        "server_name": config.app.server_name,
        "sample_time": sample_time,
        "collector_status": "ok" if sample_time else "no_data",
        "gpus": gpus,
        "users": sorted(user_list, key=lambda item: (-item["used_memory_mb"], item["username"])),
        "unknown_process_count": sum(1 for row in processes if row["username"] == "unknown"),
        "last_error": dict(error) if error else None,
    }


def today_summary(database: Database, config: Config) -> dict[str, Any]:
    today = now_local(config.app.timezone).date()
    latest_sample = latest_sample_time(database)
    key = (
        "today",
        str(database.sqlite_path),
        today.isoformat(),
        latest_sample or "none",
        report_config_hash(config),
    )
    return summary_cache().get_or_set(key, lambda: DailyAnalyzer(database, config).analyze(today))


def day_summary(database: Database, config: Config, value: str) -> dict[str, Any]:
    target = parse_local_date(value)
    today = now_local(config.app.timezone).date()
    if target == today:
        return today_summary(database, config)
    return ReportCache(database, config).generate_daily(target)


def week_summary(database: Database, config: Config, value: str) -> dict[str, Any]:
    target = parse_local_date(value)
    today = now_local(config.app.timezone).date()
    week_start, week_end, _, _ = week_bounds(target, config.app.timezone)
    if week_start <= today <= week_end:
        return current_week_summary(database, config, target)
    return ReportCache(database, config).generate_weekly(target)


def current_week_summary(database: Database, config: Config, target: date) -> dict[str, Any]:
    week_start, _week_end, _start_dt, _end_dt = week_bounds(target, config.app.timezone)
    latest_sample = latest_sample_time(database)
    key = (
        "week",
        str(database.sqlite_path),
        week_start.isoformat(),
        latest_sample or "none",
        report_config_hash(config),
    )

    def build() -> dict[str, Any]:
        today = now_local(config.app.timezone).date()
        cache = ReportCache(database, config)
        daily_summaries = []
        for day in date_range(week_start, 7):
            if day > today:
                continue
            if day == today:
                daily_summaries.append(today_summary(database, config))
            else:
                daily_summaries.append(cache.generate_daily(day))
        return WeeklyAnalyzer(database, config).analyze(target, daily_summaries=daily_summaries)

    return summary_cache().get_or_set(key, build)


def latest_sample_time(database: Database) -> str | None:
    with database.connect() as conn:
        row = conn.execute("SELECT MAX(sample_time) FROM gpu_device_snapshots").fetchone()
    return row[0] if row else None


def health_status(database: Database, config: Config) -> dict[str, Any]:
    with database.connect() as conn:
        counts = {
            "gpu_process_samples": conn.execute("SELECT COUNT(*) FROM gpu_process_samples").fetchone()[0],
            "gpu_device_snapshots": conn.execute("SELECT COUNT(*) FROM gpu_device_snapshots").fetchone()[0],
            "service_heartbeats": conn.execute("SELECT COUNT(*) FROM service_heartbeats").fetchone()[0],
            "error_events": conn.execute("SELECT COUNT(*) FROM error_events").fetchone()[0],
            "daily_reports": conn.execute("SELECT COUNT(*) FROM daily_reports").fetchone()[0],
            "weekly_reports": conn.execute("SELECT COUNT(*) FROM weekly_reports").fetchone()[0],
        }
        latest_sample = conn.execute("SELECT MAX(sample_time) FROM gpu_device_snapshots").fetchone()[0]
        latest_heartbeat = conn.execute("SELECT MAX(heartbeat_time) FROM service_heartbeats").fetchone()[0]
        latest_error = conn.execute(
            """
            SELECT event_time, event_type, severity, message
            FROM error_events
            ORDER BY event_time DESC
            LIMIT 1
            """
        ).fetchone()

    return {
        "status": "ok",
        "server_name": config.app.server_name,
        "now": isoformat(now_local(config.app.timezone)),
        "database_path": str(config.storage.sqlite_path),
        "latest_sample_time": latest_sample,
        "latest_heartbeat_time": latest_heartbeat,
        "latest_error": dict(latest_error) if latest_error else None,
        "storage": database.storage_stats(),
        "counts": counts,
        "web": {
            "host": config.web.host,
            "port": config.web.port,
            "refresh_interval_seconds": config.web.refresh_interval_seconds,
        },
    }


class SummaryCache:
    def __init__(self, max_entries: int = 32):
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, ...], dict[str, Any]] = {}

    def get_or_set(self, key: tuple[str, ...], factory) -> dict[str, Any]:
        with self._lock:
            value = self._entries.get(key)
            if value is not None:
                return value

        value = factory()
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                return existing
            self._entries[key] = value
            while len(self._entries) > self.max_entries:
                self._entries.pop(next(iter(self._entries)))
        return value


def summary_cache() -> SummaryCache:
    global _SUMMARY_CACHE
    if _SUMMARY_CACHE is None:
        _SUMMARY_CACHE = SummaryCache()
    return _SUMMARY_CACHE


def _html_shell(mode: str, value: str | None, config: Config) -> str:
    data_value = value or ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{config.app.server_name} GPU Monitor</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body data-mode="{mode}" data-value="{data_value}" data-refresh="{config.web.refresh_interval_seconds}" data-max-issues="{config.web.max_issue_items}">
  <header class="topbar">
    <div>
      <h1>{config.app.server_name}</h1>
      <p id="subtitle">GPU Monitor</p>
    </div>
    <nav>
      <a href="/">Today</a>
      <a href="/health">Health</a>
    </nav>
  </header>
  <main id="app" class="shell">
    <section class="status-line">Loading...</section>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
"""


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]
