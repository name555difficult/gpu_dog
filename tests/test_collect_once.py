from __future__ import annotations

import unittest
from pathlib import Path

from gpu_monitor.collector.models import CollectionResult
from gpu_monitor.config import parse_config
from gpu_monitor.main import collect_once


class _FakeCollector:
    def __init__(self, error: BaseException | None = None):
        self.error = error

    def collect(self) -> CollectionResult:
        if self.error is not None:
            raise self.error
        return CollectionResult(
            sample_time="2026-06-08T12:00:00+08:00",
            local_date="2026-06-08",
            snapshots=[],
            samples=[],
        )


class _FakeRepository:
    def __init__(self) -> None:
        self.collections: list[CollectionResult] = []
        self.heartbeats: list[tuple[str, str | None]] = []
        self.errors: list[tuple[str, str]] = []

    def insert_collection(self, result: CollectionResult) -> None:
        self.collections.append(result)

    def insert_heartbeat(self, status: str = "ok", message: str | None = None) -> None:
        self.heartbeats.append((status, message))

    def insert_error_event(self, event_type: str, message: str, **_kwargs: object) -> None:
        self.errors.append((event_type, message))


def _config():
    return parse_config({"storage": {"sqlite_path": str(Path("unused.db"))}})


class CollectOnceTest(unittest.TestCase):
    def test_collect_once_records_success_heartbeat_by_default(self) -> None:
        repository = _FakeRepository()

        collect_once(_config(), repository, collector=_FakeCollector())

        self.assertEqual(len(repository.collections), 1)
        self.assertEqual(repository.heartbeats, [("ok", "Collected 0 process samples")])

    def test_service_collection_can_skip_success_heartbeat(self) -> None:
        repository = _FakeRepository()

        collect_once(_config(), repository, collector=_FakeCollector(), record_success_heartbeat=False)

        self.assertEqual(len(repository.collections), 1)
        self.assertEqual(repository.heartbeats, [])

    def test_collection_error_still_records_error_and_heartbeat(self) -> None:
        repository = _FakeRepository()

        collect_once(
            _config(),
            repository,
            collector=_FakeCollector(RuntimeError("nvidia-smi failed")),
            record_success_heartbeat=False,
        )

        self.assertEqual(repository.errors, [("collector_error", "nvidia-smi failed")])
        self.assertEqual(repository.heartbeats, [("error", "nvidia-smi failed")])


if __name__ == "__main__":
    unittest.main()
