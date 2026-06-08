from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gpu_monitor.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GPU Monitor acceptance checks")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--skip-service", action="store_true", help="Skip run-service HTTP checks")
    args = parser.parse_args()

    config = load_config(args.config)
    base_url = f"http://{config.web.host}:{config.web.port}"

    checks = [
        ("compile", [sys.executable, "-m", "compileall", "gpu_monitor", "tests", "scripts"]),
        ("unit tests", [sys.executable, "-m", "unittest", "discover", "-v"]),
        ("init db", [sys.executable, "-m", "gpu_monitor.main", "--config", args.config, "init-db"]),
        ("collect once", [sys.executable, "-m", "gpu_monitor.main", "--config", args.config, "collect-once"]),
        ("generate daily", [sys.executable, "-m", "gpu_monitor.main", "--config", args.config, "generate-daily", "--force"]),
        ("generate weekly", [sys.executable, "-m", "gpu_monitor.main", "--config", args.config, "generate-weekly", "--force"]),
        ("cleanup", [sys.executable, "-m", "gpu_monitor.main", "--config", args.config, "cleanup"]),
        ("compact db", [sys.executable, "-m", "gpu_monitor.main", "--config", args.config, "compact-db"]),
    ]

    for name, command in checks:
        run_check(name, command)

    if shutil.which("systemd-analyze"):
        run_systemd_verify()

    if not args.skip_service:
        run_service_checks(args.config, base_url)

    print("ACCEPTANCE OK")
    return 0


def run_check(name: str, command: list[str]) -> None:
    print(f"==> {name}: {' '.join(command)}")
    subprocess.run(command, check=True)


def run_systemd_verify() -> None:
    source = Path("systemd/gpu-monitor.service")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / source.name
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        target.chmod(0o644)
        run_check("systemd verify", ["systemd-analyze", "verify", str(target)])


def run_service_checks(config_path: str, base_url: str) -> None:
    print("==> service: start")
    process = subprocess.Popen(
        [sys.executable, "-m", "gpu_monitor.main", "--config", config_path, "run"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_for_http(base_url + "/api/health", timeout_seconds=20)
        endpoints = [
            "/",
            "/api/health",
            "/api/current",
            "/api/today",
            "/api/day?date=2026-06-07",
            "/api/week?date=2026-06-07",
            "/export/day?date=2026-06-07",
            "/export/week?date=2026-06-07",
            "/day/2026-06-07",
            "/week/2026-06-07",
            "/static/app.js",
            "/static/style.css",
        ]
        for endpoint in endpoints:
            response = request(base_url + endpoint)
            assert_status(endpoint, response, "200")
            if endpoint.startswith("/api/"):
                payload = json.loads(response.body)
                if endpoint == "/api/current":
                    require_keys(payload, ["collector_status", "gpus", "users", "sample_time"])
                if endpoint == "/api/today":
                    require_keys(payload, ["overview", "users", "gpus", "user_gpu"])
                if endpoint == "/api/health":
                    require_keys(payload, ["status", "counts", "latest_sample_time", "storage"])
            if endpoint.startswith("/export/") and not response.body.startswith("# GPU "):
                raise AssertionError(f"{endpoint} did not return markdown")
        print("==> service endpoints: ok")
    finally:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=10)
        tail = "\n".join((output or "").splitlines()[-12:])
        if tail:
            print("==> service tail")
            print(tail)


def wait_for_http(url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = request(url)
            if " 200 " in response.status_line:
                return
        except OSError as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


class Response:
    def __init__(self, status_line: str, body: str):
        self.status_line = status_line
        self.body = body


def request(url: str) -> Response:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    with socket.create_connection((host, port), timeout=5) as sock:
        request_bytes = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode("ascii")
        sock.sendall(request_bytes)
        chunks = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)
    raw = b"".join(chunks).decode("utf-8", "replace")
    headers, _, body = raw.partition("\r\n\r\n")
    return Response(headers.splitlines()[0], body)


def assert_status(endpoint: str, response: Response, code: str) -> None:
    if f" {code} " not in response.status_line:
        raise AssertionError(f"{endpoint} returned {response.status_line}")


def require_keys(payload: dict, keys: list[str]) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise AssertionError(f"Missing keys: {missing}")


if __name__ == "__main__":
    raise SystemExit(main())
