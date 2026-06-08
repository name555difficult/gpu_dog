from __future__ import annotations

import logging

import psutil

logger = logging.getLogger(__name__)


class ProcessResolver:
    def __init__(self) -> None:
        self._username_cache: dict[int, str] = {}

    def username_for_pid(self, pid: int) -> str:
        try:
            username = psutil.Process(pid).username()
            if username and username != "unknown":
                self._username_cache[pid] = username
            return username
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
            cached_username = self._username_cache.get(pid)
            if cached_username:
                logger.debug("Using cached username %s for pid %s after resolver error: %s", cached_username, pid, exc)
                return cached_username
            logger.debug("Unable to resolve username for pid %s: %s", pid, exc)
            return "unknown"
