from __future__ import annotations

import argparse
import json
import socket
from urllib.parse import urlparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the local GPU Monitor dashboard")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    for path in ["/api/health", "/api/current", "/api/today"]:
        payload = _request_json(base + path)
        print(path, "ok", sorted(payload.keys())[:8])
    for path in ["/export/day", "/export/week"]:
        body = _request_text(base + path)
        if not body.startswith("# GPU "):
            raise RuntimeError(f"{path} did not return markdown")
        print(path, "ok", body.splitlines()[0])
    return 0


def _request_json(url: str) -> dict:
    return json.loads(_request_text(url))


def _request_text(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http":
        raise ValueError("Only http:// URLs are supported")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    with socket.create_connection((host, port), timeout=5) as sock:
        request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        sock.sendall(request.encode("ascii"))
        chunks = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)

    raw = b"".join(chunks).decode("utf-8", "replace")
    headers, _, body = raw.partition("\r\n\r\n")
    status_line = headers.splitlines()[0]
    if " 200 " not in status_line:
        raise RuntimeError(f"{url} returned {status_line}")
    return body


if __name__ == "__main__":
    raise SystemExit(main())
