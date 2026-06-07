from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
from pathlib import Path

from gpu_monitor.collector.nvidia_smi_collector import NvidiaSmiCollector
from gpu_monitor.config import Config, load_config
from gpu_monitor.logging_config import configure_logging
from gpu_monitor.storage.database import Database
from gpu_monitor.storage.repositories import MonitorRepository

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GPU usage monitor")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--log-path", default="logs/gpu-monitor.log", help="Path to log file")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init-db", help="Initialize SQLite database")
    subparsers.add_parser("collect-once", help="Run one GPU collection cycle and exit")
    subparsers.add_parser("run", help="Run collector and heartbeat loops")
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

    if command == "run":
        run_service(config, repository)
        return 0

    raise ValueError(f"Unknown command: {command}")


def collect_once(config: Config, repository: MonitorRepository) -> None:
    if config.collector.backend != "nvidia-smi":
        raise ValueError(f"Unsupported collector backend: {config.collector.backend}")

    collector = NvidiaSmiCollector(
        timezone=config.app.timezone,
        timeout_seconds=config.collector.command_timeout_seconds,
    )

    try:
        result = collector.collect()
        repository.insert_collection(result)
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

    logger.info("Starting GPU monitor service with config-backed data path %s", config.storage.sqlite_path)
    collector_thread.start()
    heartbeat_thread.start()

    while not stop_event.is_set():
        time.sleep(0.5)

    collector_thread.join(timeout=5)
    heartbeat_thread.join(timeout=5)
    logger.info("GPU monitor service stopped")


def _collector_loop(config: Config, repository: MonitorRepository, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        start = time.monotonic()
        collect_once(config, repository)
        elapsed = time.monotonic() - start
        sleep_seconds = max(0.0, config.collector.sample_interval_seconds - elapsed)
        if elapsed > config.collector.sample_interval_seconds:
            logger.warning(
                "Collection cycle took %.2fs, longer than interval %ss",
                elapsed,
                config.collector.sample_interval_seconds,
            )
        stop_event.wait(sleep_seconds)


def _heartbeat_loop(config: Config, repository: MonitorRepository, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            repository.insert_heartbeat("ok", "heartbeat")
        except Exception:
            logger.exception("Heartbeat write failed")
        stop_event.wait(config.heartbeat.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
