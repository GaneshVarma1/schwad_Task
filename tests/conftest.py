import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TOKEN = "test-only-token-that-is-at-least-32-bytes"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        api_key=TOKEN, database_path=str(tmp_path / "test.db"), create_limit_per_minute=1000
    )


@pytest.fixture
def now():
    return [1800000000]


@pytest.fixture
def app(settings, now):
    return create_app(settings, clock=lambda: now[0])


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}
