from __future__ import annotations

import logging

import psutil

logger = logging.getLogger(__name__)


class ProcessResolver:
    def username_for_pid(self, pid: int) -> str:
        try:
            return psutil.Process(pid).username()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
            logger.debug("Unable to resolve username for pid %s: %s", pid, exc)
            return "unknown"
