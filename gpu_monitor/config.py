from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    server_name: str
    timezone: str


@dataclass(frozen=True)
class WebConfig:
    enabled: bool
    host: str
    port: int
    refresh_interval_seconds: int
    max_issue_items: int


@dataclass(frozen=True)
class CollectorConfig:
    backend: str
    sample_interval_seconds: int
    active_memory_threshold_mb: int
    command_timeout_seconds: int


@dataclass(frozen=True)
class SessionConfig:
    gap_threshold_seconds: int


@dataclass(frozen=True)
class HeartbeatConfig:
    interval_seconds: int
    missing_threshold_seconds: int


@dataclass(frozen=True)
class ReportsConfig:
    cache_dir: Path
    daily_generate_time: str
    weekly_generate_day: str
    weekly_generate_time: str


@dataclass(frozen=True)
class CleanupConfig:
    raw_retention_days: int
    gpu_snapshot_retention_days: int
    daily_cache_retention_days: int
    weekly_cache_retention_weeks: int
    error_log_retention_days: int
    heartbeat_retention_days: int
    compact_after_cleanup: bool
    compact_min_freelist_ratio: float


@dataclass(frozen=True)
class StorageConfig:
    sqlite_path: Path
    cleanup: CleanupConfig


@dataclass(frozen=True)
class UsersConfig:
    alias: dict[str, str]


@dataclass(frozen=True)
class Config:
    app: AppConfig
    web: WebConfig
    collector: CollectorConfig
    session: SessionConfig
    heartbeat: HeartbeatConfig
    reports: ReportsConfig
    storage: StorageConfig
    users: UsersConfig


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> Config:
    app = raw.get("app", {})
    web = raw.get("web", {})
    collector = raw.get("collector", {})
    session = raw.get("session", {})
    heartbeat = raw.get("heartbeat", {})
    reports = raw.get("reports", {})
    storage = raw.get("storage", {})
    cleanup = storage.get("cleanup", {})
    users = raw.get("users", {})

    return Config(
        app=AppConfig(
            server_name=str(app.get("server_name", "gpu-server")),
            timezone=str(app.get("timezone", "Asia/Shanghai")),
        ),
        web=WebConfig(
            enabled=bool(web.get("enabled", True)),
            host=str(web.get("host", "127.0.0.1")),
            port=int(web.get("port", 8765)),
            refresh_interval_seconds=int(web.get("refresh_interval_seconds", 60)),
            max_issue_items=int(web.get("max_issue_items", 5)),
        ),
        collector=CollectorConfig(
            backend=str(collector.get("backend", "nvidia-smi")),
            sample_interval_seconds=int(collector.get("sample_interval_seconds", 60)),
            active_memory_threshold_mb=int(collector.get("active_memory_threshold_mb", 100)),
            command_timeout_seconds=int(collector.get("command_timeout_seconds", 10)),
        ),
        session=SessionConfig(
            gap_threshold_seconds=int(session.get("gap_threshold_seconds", 300)),
        ),
        heartbeat=HeartbeatConfig(
            interval_seconds=int(heartbeat.get("interval_seconds", 60)),
            missing_threshold_seconds=int(heartbeat.get("missing_threshold_seconds", 300)),
        ),
        reports=ReportsConfig(
            cache_dir=Path(reports.get("cache_dir", "data/reports")),
            daily_generate_time=str(reports.get("daily", {}).get("generate_time", "00:05")),
            weekly_generate_day=str(reports.get("weekly", {}).get("generate_day", "monday")),
            weekly_generate_time=str(reports.get("weekly", {}).get("generate_time", "00:10")),
        ),
        storage=StorageConfig(
            sqlite_path=Path(storage.get("sqlite_path", "data/monitor.db")),
            cleanup=CleanupConfig(
                raw_retention_days=int(cleanup.get("raw_retention_days", 3)),
                gpu_snapshot_retention_days=int(cleanup.get("gpu_snapshot_retention_days", 3)),
                daily_cache_retention_days=int(cleanup.get("daily_cache_retention_days", 14)),
                weekly_cache_retention_weeks=int(cleanup.get("weekly_cache_retention_weeks", 12)),
                error_log_retention_days=int(cleanup.get("error_log_retention_days", 7)),
                heartbeat_retention_days=int(cleanup.get("heartbeat_retention_days", 7)),
                compact_after_cleanup=bool(cleanup.get("compact_after_cleanup", True)),
                compact_min_freelist_ratio=float(cleanup.get("compact_min_freelist_ratio", 0.15)),
            ),
        ),
        users=UsersConfig(alias={str(k): str(v) for k, v in users.get("alias", {}).items()}),
    )
