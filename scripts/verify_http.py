"""Start a real server against an isolated database; verify HTTP and measure a small local burst."""

import json
import os
import platform
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median

import httpx

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="shortener-verify-") as temporary:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        token = secrets.token_urlsafe(32)
        db_path = str(Path(temporary) / "verify.db")
        environment = {
            **os.environ,
            "SHORTENER_API_KEY": token,
            "SHORTENER_DATABASE": db_path,
            "SHORTENER_BASE_URL": origin,
        }
        with tempfile.TemporaryFile(mode="w+") as logs:
            process = subprocess.Popen(  # noqa: S603 - fixed local interpreter/module and arguments
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                ],
                cwd=ROOT,
                env=environment,
                stdout=logs,
                stderr=logs,
            )
            try:
                with httpx.Client(
                    base_url=origin, timeout=10, follow_redirects=False, trust_env=False
                ) as client:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            if client.get("/ready").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if time.monotonic() >= deadline or process.poll() is not None:
                            raise RuntimeError("Server failed to become ready")
                        time.sleep(0.05)
                    auth = {"Authorization": f"Bearer {token}", "Idempotency-Key": "http-demo-key"}
                    payload = {"url": "https://example.com/engineering", "custom_alias": "httpdemo"}
                    first = client.post("/api/v1/links", headers=auth, json=payload)
                    require(first.status_code == 201, "Create failed")
                    retry = client.post("/api/v1/links", headers=auth, json=payload)
                    require(
                        retry.status_code == 200 and first.json() == retry.json(), "Replay failed"
                    )
                    require(
                        client.get("/api/v1/links/httpdemo/analytics").status_code == 401,
                        "Analytics exposed without authentication",
                    )
                    require(client.head("/httpdemo").status_code == 302, "HEAD failed")

                    def redirect(_):
                        start = time.perf_counter()
                        result = client.get("/httpdemo")
                        require(result.status_code == 302, "Redirect failed")
                        require(result.headers["location"] == payload["url"], "Destination changed")
                        return (time.perf_counter() - start) * 1000

                    start = time.perf_counter()
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        durations = list(pool.map(redirect, range(250)))
                    elapsed = time.perf_counter() - start
                    stats = client.get("/api/v1/links/httpdemo/analytics", headers=auth).json()
                    require(stats["total_clicks"] == 250, "Lost or extra click counts")
                    with sqlite3.connect(db_path) as db:
                        require(
                            db.execute("SELECT total_clicks FROM links").fetchone()[0] == 250,
                            "HTTP result did not persist",
                        )
                        require(
                            db.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                            "Integrity check failed",
                        )
                    require(
                        client.delete("/api/v1/links/httpdemo", headers=auth).status_code == 204,
                        "Disable failed",
                    )
                    require(
                        client.get("/httpdemo").status_code == 410, "Disabled link still active"
                    )
                    require(
                        client.get("/api/v1/links/httpdemo/analytics", headers=auth).json()[
                            "total_clicks"
                        ]
                        == 250,
                        "Disabled request was counted",
                    )
                    report = {
                        "status": "passed",
                        "python": platform.python_version(),
                        "platform": platform.platform(),
                        "sqlite": sqlite3.sqlite_version,
                        "transport": "real HTTP over loopback; uvicorn; SQLite WAL",
                        "verified": [
                            "create",
                            "idempotent replay",
                            "auth",
                            "HEAD",
                            "redirect",
                            "durable analytics",
                            "disable",
                            "integrity_check",
                        ],
                        "requests": 250,
                        "concurrency": 8,
                        "failures": 0,
                        "elapsed_seconds": round(elapsed, 3),
                        "requests_per_second": round(250 / elapsed, 1),
                        "latency_ms_p50": round(median(durations), 2),
                        "latency_ms_p95": round(sorted(durations)[237], 2),
                        "limitation": "Local smoke benchmark; not a production capacity claim",
                    }
                    print(json.dumps(report, indent=2))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                logs.seek(0)
                output = logs.read()
                if token in output or "example.com/engineering" in output:
                    raise RuntimeError("Sensitive value appeared in server logs")


if __name__ == "__main__":
    main()
