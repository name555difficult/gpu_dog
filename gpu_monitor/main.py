from __future__ import annotations

import argparse
import logging
import signal
import threading
import time

from gpu_monitor.cleanup.cleanup_manager import CleanupManager
from gpu_monitor.collector.nvidia_smi_collector import NvidiaSmiCollector
from gpu_monitor.config import Config, load_config
from gpu_monitor.logging_config import configure_logging
from gpu_monitor.reports.json_cache import ReportCache
from gpu_monitor.scheduler.jobs import SimpleScheduler, parse_job_date
from gpu_monitor.storage.database import Database
from gpu_monitor.storage.repositories import MonitorRepository
from gpu_monitor.web.dashboard import run_dashboard_server

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GPU usage monitor")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--log-path", default="logs/gpu-monitor.log", help="Path to log file")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init-db", help="Initialize SQLite database")
    subparsers.add_parser("collect-once", help="Run one GPU collection cycle and exit")
    subparsers.add_parser("run", help="Run collector, heartbeat, dashboard, and scheduler loops")
    subparsers.add_parser("status", help="Print database row counts")
    subparsers.add_parser("compact-db", help="Checkpoint and vacuum SQLite storage")

    daily_parser = subparsers.add_parser("generate-daily", help="Generate daily JSON cache")
    daily_parser.add_argument("--date", help="Date in YYYY-MM-DD format; defaults to today")
    daily_parser.add_argument("--force", action="store_true", help="Regenerate even if cache exists")

    weekly_parser = subparsers.add_parser("generate-weekly", help="Generate weekly JSON cache")
    weekly_parser.add_argument("--date", help="Any date in the target week; defaults to today")
    weekly_parser.add_argument("--force", action="store_true", help="Regenerate even if cache exists")

    subparsers.add_parser("cleanup", help="Run retention cleanup once")

    repair_parser = subparsers.add_parser(
        "repair-unknown-users",
        help="Backfill unknown usernames when the same PID has a known username in nearby samples",
    )
    repair_parser.add_argument("--dry-run", action="store_true", help="Print repairs without updating SQLite")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_path)
    config = load_config(args.config)

    command = args.command or "run"
    database = Database(config.storage.sqlite_path)
    repository = MonitorRepository(database, config.app.timezone)

    if command == "init-db":
        database.initialize()
        logger.info("Initialized database at %s", config.storage.sqlite_path)
        return 0

    database.initialize()

    if command == "collect-once":
        collect_once(config, repository)
        logger.info("Database row counts: %s", repository.latest_counts())
        return 0

    if command == "status":
        logger.info("Database row counts: %s", repository.latest_counts())
        logger.info("Database storage stats: %s", database.storage_stats())
        return 0

    if command == "generate-daily":
        target = parse_job_date(args.date, config.app.timezone)
        summary = ReportCache(database, config).generate_daily(target, force=args.force)
        logger.info("Generated daily cache for %s: %s", target, summary["overview"])
        return 0

    if command == "generate-weekly":
        target = parse_job_date(args.date, config.app.timezone)
        summary = ReportCache(database, config).generate_weekly(target, force=args.force)
        logger.info("Generated weekly cache for %s: %s", target, summary["overview"])
        return 0

    if command == "cleanup":
        logger.info("Cleanup result: %s", CleanupManager(database, config).run())
        return 0

    if command == "compact-db":
        logger.info("Compact result: %s", database.compact())
        return 0

    if command == "repair-unknown-users":
        repairs = repository.repair_unknown_users(dry_run=args.dry_run)
        logger.info("%s unknown user repairs%s", len(repairs), " (dry run)" if args.dry_run else "")
        for repair in repairs:
            logger.info("repair: %s", repair)
        return 0

    if command == "run":
        run_service(config, repository)
        return 0

    raise ValueError(f"Unknown command: {command}")


def collect_once(
    config: Config,
    repository: MonitorRepository,
    collector: NvidiaSmiCollector | None = None,
    record_success_heartbeat: bool = True,
) -> None:
    if config.collector.backend != "nvidia-smi":
        raise ValueError(f"Unsupported collector backend: {config.collector.backend}")

    if collector is None:
        collector = build_collector(config)

    try:
        result = collector.collect()
        repository.insert_collection(result)
        if record_success_heartbeat:
            repository.insert_heartbeat("ok", f"Collected {len(result.samples)} process samples")
        logger.info(
            "Collected %s GPU snapshots and %s process samples at %s",
            len(result.snapshots),
            len(result.samples),
            result.sample_time,
        )
    except Exception as exc:
        logger.exception("GPU collection failed")
        repository.insert_error_event("collector_error", str(exc), exc=exc)
        repository.insert_heartbeat("error", str(exc))


def run_service(config: Config, repository: MonitorRepository) -> None:
    stop_event = threading.Event()

    def request_stop(signum: int, _frame: object) -> None:
        logger.info("Received signal %s, stopping service", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    collector_thread = threading.Thread(
        target=_collector_loop,
        name="collector-loop",
        args=(config, repository, stop_event),
        daemon=True,
    )
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        name="heartbeat-loop",
        args=(config, repository, stop_event),
        daemon=True,
    )
    scheduler = SimpleScheduler(repository.database, config)
    scheduler_thread = threading.Thread(
        target=scheduler.run_loop,
        name="scheduler-loop",
        args=(stop_event,),
        daemon=True,
    )
    dashboard_thread = None
    if config.web.enabled:
        dashboard_thread = threading.Thread(
            target=run_dashboard_server,
            name="dashboard-server",
            args=(config, repository.database, stop_event),
            daemon=True,
        )

    logger.info("Starting GPU monitor service with config-backed data path %s", config.storage.sqlite_path)
    scheduler.run_startup_compensation()
    collector_thread.start()
    heartbeat_thread.start()
    scheduler_thread.start()
    if dashboard_thread is not None:
        dashboard_thread.start()

    while not stop_event.is_set():
        time.sleep(0.5)

    collector_thread.join(timeout=5)
    heartbeat_thread.join(timeout=5)
    scheduler_thread.join(timeout=5)
    if dashboard_thread is not None:
        dashboard_thread.join(timeout=5)
    logger.info("GPU monitor service stopped")


def _collector_loop(config: Config, repository: MonitorRepository, stop_event: threading.Event) -> None:
    collector = build_collector(config)
    while not stop_event.is_set():
        start = time.monotonic()
        collect_once(config, repository, collector=collector, record_success_heartbeat=False)
        elapsed = time.monotonic() - start
        sleep_seconds = max(0.0, config.collector.sample_interval_seconds - elapsed)
        if elapsed > config.collector.sample_interval_seconds:
            logger.warning(
                "Collection cycle took %.2fs, longer than interval %ss",
                elapsed,
                config.collector.sample_interval_seconds,
            )
        stop_event.wait(sleep_seconds)


def build_collector(config: Config) -> NvidiaSmiCollector:
    return NvidiaSmiCollector(
        timezone=config.app.timezone,
        timeout_seconds=config.collector.command_timeout_seconds,
    )


def _heartbeat_loop(config: Config, repository: MonitorRepository, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            repository.insert_heartbeat("ok", "heartbeat")
        except Exception:
            logger.exception("Heartbeat write failed")
        stop_event.wait(config.heartbeat.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
