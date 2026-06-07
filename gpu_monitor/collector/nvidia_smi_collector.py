from __future__ import annotations

import csv
import logging
import subprocess
from dataclasses import dataclass

from gpu_monitor.collector.models import CollectionResult, GpuDeviceSnapshot, GpuProcessSample
from gpu_monitor.collector.process_resolver import ProcessResolver
from gpu_monitor.utils.time_utils import isoformat, local_date, now_local

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GpuInfo:
    gpu_index: int
    gpu_uuid: str
    gpu_name: str | None
    total_memory_mb: float | None
    gpu_util_percent: float | None
    memory_util_percent: float | None


class NvidiaSmiCollector:
    def __init__(self, timezone: str, timeout_seconds: int, resolver: ProcessResolver | None = None):
        self.timezone = timezone
        self.timeout_seconds = timeout_seconds
        self.resolver = resolver or ProcessResolver()

    def collect(self) -> CollectionResult:
        sample_dt = now_local(self.timezone)
        sample_time = isoformat(sample_dt)
        date = local_date(sample_dt)
        created_at = sample_time

        gpu_infos = self._query_gpus()
        snapshots = [
            GpuDeviceSnapshot(
                sample_time=sample_time,
                local_date=date,
                gpu_index=info.gpu_index,
                gpu_uuid=info.gpu_uuid,
                gpu_name=info.gpu_name,
                total_memory_mb=info.total_memory_mb,
                gpu_util_percent=info.gpu_util_percent,
                memory_util_percent=info.memory_util_percent,
                created_at=created_at,
            )
            for info in gpu_infos.values()
        ]

        samples = self._query_process_samples(gpu_infos, sample_time, date, created_at)
        return CollectionResult(sample_time=sample_time, local_date=date, snapshots=snapshots, samples=samples)

    def _query_gpus(self) -> dict[str, GpuInfo]:
        output = self._run_nvidia_smi(
            [
                "--query-gpu=index,uuid,name,memory.total,utilization.gpu,utilization.memory",
                "--format=csv,noheader,nounits",
            ]
        )
        gpu_infos: dict[str, GpuInfo] = {}
        for row in _csv_rows(output):
            if len(row) < 6:
                logger.warning("Skipping malformed GPU row: %s", row)
                continue
            gpu_index = _parse_int(row[0])
            gpu_uuid = row[1]
            if gpu_index is None or not gpu_uuid:
                logger.warning("Skipping GPU row without index/uuid: %s", row)
                continue
            gpu_infos[gpu_uuid] = GpuInfo(
                gpu_index=gpu_index,
                gpu_uuid=gpu_uuid,
                gpu_name=row[2] or None,
                total_memory_mb=_parse_float(row[3]),
                gpu_util_percent=_parse_float(row[4]),
                memory_util_percent=_parse_float(row[5]),
            )
        return gpu_infos

    def _query_process_samples(
        self,
        gpu_infos: dict[str, GpuInfo],
        sample_time: str,
        date: str,
        created_at: str,
    ) -> list[GpuProcessSample]:
        output = self._run_nvidia_smi(
            [
                "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ]
        )
        samples: list[GpuProcessSample] = []
        for row in _csv_rows(output):
            if len(row) < 4:
                logger.warning("Skipping malformed process row: %s", row)
                continue
            gpu_uuid = row[0]
            gpu_info = gpu_infos.get(gpu_uuid)
            if gpu_info is None:
                logger.warning("Skipping process row with unknown GPU uuid %s: %s", gpu_uuid, row)
                continue

            pid = _parse_int(row[1])
            used_memory_mb = _parse_float(row[3])
            if pid is None or used_memory_mb is None:
                logger.warning("Skipping process row without pid/memory: %s", row)
                continue

            samples.append(
                GpuProcessSample(
                    sample_time=sample_time,
                    local_date=date,
                    gpu_index=gpu_info.gpu_index,
                    gpu_uuid=gpu_uuid,
                    pid=pid,
                    username=self.resolver.username_for_pid(pid),
                    process_name=row[2] or None,
                    used_memory_mb=used_memory_mb,
                    created_at=created_at,
                )
            )
        return samples

    def _run_nvidia_smi(self, args: list[str]) -> str:
        command = ["nvidia-smi", *args]
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        return completed.stdout


def _csv_rows(output: str) -> list[list[str]]:
    if not output.strip():
        return []
    return [[cell.strip() for cell in row] for row in csv.reader(output.splitlines()) if row]


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
