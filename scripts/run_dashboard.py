"""Run a local dashboard sandbox with an isolated temporary database and synthetic analytics."""

import argparse
import secrets
import tempfile
import time
from pathlib import Path

import uvicorn

from app.config import Settings
from app.demo import seed_demo
from app.main import create_app
from app.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="schwab-link-demo-") as directory:
        settings = Settings(
            api_key=secrets.token_urlsafe(32),
            database_path=str(Path(directory) / "demo.db"),
            base_url=f"http://127.0.0.1:{args.port}",
            demo_mode=True,
        )
        store = Store(settings)
        store.initialize()
        seed_demo(store, int(time.time()))
        print(
            f"Schwab Link Manager demo: {settings.base_url} "
            "(interview prototype; synthetic data; resets when stopped)",
            flush=True,
        )
        uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
