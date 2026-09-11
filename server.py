"""Entry point for the explicitly non-production interview demo."""

import os
import secrets
import tempfile
import time
from pathlib import Path

from app.config import Settings
from app.demo import seed_demo
from app.main import create_app
from app.store import Store


def deployment_origin():
    explicit = os.environ.get("SHORTENER_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or os.environ.get("VERCEL_URL")
    return f"https://{host}" if host else "http://127.0.0.1:8000"


def demo_database():
    # A durable path keeps one database behind every request. A per-instance
    # temporary directory splits state as soon as the platform runs more than one
    # instance: a link created on one instance is missing from all the others.
    configured = os.environ.get("SHORTENER_DATABASE")
    return configured or str(Path(tempfile.gettempdir()) / "schwab-link-manager-demo.db")


settings = Settings(
    api_key=secrets.token_urlsafe(32),
    database_path=demo_database(),
    base_url=deployment_origin(),
    demo_mode=True,
)

seed_store = Store(settings)
seed_store.initialize()
if seed_store.dashboard(int(time.time()), days=1)["total_links"] == 0:
    seed_demo(seed_store, int(time.time()))

app = create_app(settings)
