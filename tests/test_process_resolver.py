from __future__ import annotations

import unittest
from unittest.mock import patch

import psutil

from gpu_monitor.collector.process_resolver import ProcessResolver


class _FakeProcess:
    def __init__(self, username: str):
        self._username = username

    def username(self) -> str:
        return self._username


class ProcessResolverTest(unittest.TestCase):
    def test_uses_cached_username_when_pid_disappears(self) -> None:
        resolver = ProcessResolver()
        with patch("gpu_monitor.collector.process_resolver.psutil.Process", return_value=_FakeProcess("yzt")):
            self.assertEqual(resolver.username_for_pid(123), "yzt")

        with patch(
            "gpu_monitor.collector.process_resolver.psutil.Process",
            side_effect=psutil.NoSuchProcess(pid=123),
        ):
            self.assertEqual(resolver.username_for_pid(123), "yzt")


if __name__ == "__main__":
    unittest.main()
