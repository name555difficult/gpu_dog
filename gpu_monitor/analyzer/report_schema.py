from __future__ import annotations

import hashlib
import json

from gpu_monitor.config import Config

SUMMARY_SCHEMA_VERSION = 3


def report_config_hash(config: Config) -> str:
    payload = {
        "schema": SUMMARY_SCHEMA_VERSION,
        "timezone": config.app.timezone,
        "sample_interval_seconds": config.collector.sample_interval_seconds,
        "active_memory_threshold_mb": config.collector.active_memory_threshold_mb,
        "session_gap_threshold_seconds": config.session.gap_threshold_seconds,
        "session_merge_gap_threshold_seconds": config.session.merge_gap_threshold_seconds,
        "heartbeat_missing_threshold_seconds": config.heartbeat.missing_threshold_seconds,
        "user_alias": config.users.alias,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
