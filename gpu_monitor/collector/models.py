from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GpuDeviceSnapshot:
    sample_time: str
    local_date: str
    gpu_index: int
    gpu_uuid: str | None
    gpu_name: str | None
    total_memory_mb: float | None
    gpu_util_percent: float | None
    memory_util_percent: float | None
    created_at: str


@dataclass(frozen=True)
class GpuProcessSample:
    sample_time: str
    local_date: str
    gpu_index: int
    gpu_uuid: str | None
    pid: int
    username: str
    process_name: str | None
    used_memory_mb: float
    created_at: str


@dataclass(frozen=True)
class CollectionResult:
    sample_time: str
    local_date: str
    snapshots: list[GpuDeviceSnapshot]
    samples: list[GpuProcessSample]
