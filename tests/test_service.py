from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import CreateLink
from app.store import DomainError, Store


def create(client, auth, **payload):
    return client.post(
        "/api/v1/links",
        headers=auth,
        json={"url": "https://example.com/article?q=1#section", **payload},
    )


def test_end_to_end(client, auth):
    response = create(client, auth, custom_alias="demo")
    assert response.status_code == 201
    assert response.headers["location"] == "/api/v1/links/demo"
    assert response.json()["short_url"] == "http://127.0.0.1:8000/demo"
    assert client.get("/api/v1/links/demo", headers=auth).json()["disabled"] is False
    redirect = client.get("/demo", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "https://example.com/article?q=1#section"
    assert redirect.headers["cache-control"] == "no-store"
    assert redirect.headers["referrer-policy"] == "no-referrer"
    assert len(redirect.headers["x-request-id"]) == 32
    assert client.head("/demo", follow_redirects=False).status_code == 302
    stats = client.get("/api/v1/links/demo/analytics", headers=auth).json()
    assert stats["total_clicks"] == 1
    assert stats["daily"][0]["clicks"] == 1
    assert client.delete("/api/v1/links/demo", headers=auth).status_code == 204
    assert client.delete("/api/v1/links/demo", headers=auth).status_code == 204
    assert client.get("/demo").status_code == 410
    assert client.get("/api/v1/links/demo/analytics", headers=auth).json()["total_clicks"] == 1


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/v1/links"),
        ("get", "/api/v1/links/demo"),
        ("delete", "/api/v1/links/demo"),
        ("get", "/api/v1/links/demo/analytics"),
    ],
)
def test_management_requires_auth(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "ftp://example.com",
        "https://u:p@example.com",
        "http://localhost",
        "http://127.0.0.1",
        "http://[::1]",
        "http://10.0.0.1",
        "https://example.com\r\nX-Bad: yes",
        "https://example.com/%0d%0afoo",
        "http://example.com\\@evil.com",
        "https://example.com:99999",
        "https://bad_host.com",
        "http://2130706433",
        "http://127.1",
        "http://service.internal",
        "https://-bad.com",
        "https://example.com:0",
        "https://[broken",
        "https://example.com/a b",
    ],
)
def test_unsafe_urls_rejected(client, auth, url):
    response = create(client, auth, url=url)
    assert response.status_code == 422
    assert url not in response.text


@pytest.mark.parametrize("alias", ["abc", "a" * 33, "bad/name", "docs", "HEALTH", "demo!"])
def test_alias_validation(client, auth, alias):
    assert create(client, auth, custom_alias=alias).status_code == 422


def test_conflict_and_missing(client, auth):
    assert create(client, auth, custom_alias="same").status_code == 201
    assert create(client, auth, custom_alias="same").status_code == 409
    for path in ["/missing", "/api/v1/links/missing", "/api/v1/links/missing/analytics"]:
        assert client.get(path, headers=auth).status_code == 404
    assert client.delete("/api/v1/links/missing", headers=auth).status_code == 404


def test_expiration_boundary(client, auth, now):
    expiry = datetime.fromtimestamp(now[0] + 10, UTC).isoformat()
    assert create(client, auth, custom_alias="expire", expires_at=expiry).status_code == 201
    assert client.get("/expire", follow_redirects=False).status_code == 302
    now[0] += 10
    assert client.get("/expire").status_code == 410
    assert client.head("/expire").status_code == 410
    assert create(client, auth, expires_at=expiry).status_code == 422
    assert create(client, auth, expires_at="2030-01-01T00:00:00").status_code == 422


def test_daily_buckets(client, auth, now):
    create(client, auth, custom_alias="daily")
    client.get("/daily", follow_redirects=False)
    now[0] += 86400
    client.get("/daily", follow_redirects=False)
    stats = client.get("/api/v1/links/daily/analytics", headers=auth).json()
    assert stats["total_clicks"] == 2
    assert len(stats["daily"]) == 2


def test_parallel_clicks_no_lost_updates(client, auth, app, now):
    create(client, auth, custom_alias="parallel")
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: app.state.store.resolve("parallel", now[0]), range(100)))
    assert len(results) == 100
    stats = app.state.store.analytics("parallel")
    assert stats["total_clicks"] == sum(x["clicks"] for x in stats["daily"]) == 100


def test_parallel_alias_uniqueness(client, app, now):
    def attempt(_):
        try:
            app.state.store.create(
                CreateLink(url="https://example.com", custom_alias="shared"), now[0]
            )
            return 201
        except DomainError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(attempt, range(16)))
    assert statuses.count(201) == 1
    assert statuses.count(409) == 15


def test_collision_retry(client, auth):
    create(client, auth, custom_alias="occupied")
    with patch("app.store.secrets.token_urlsafe", side_effect=["occupied", "fresh123"]):
        assert create(client, auth).json()["code"] == "fresh123"
    with patch("app.store.secrets.token_urlsafe", return_value="occupied"):
        result = create(client, auth)
        assert result.status_code == 503
        assert result.headers["retry-after"] == "1"


def test_storage_lock_returns_503(settings, now, auth):
    app = create_app(replace(settings, busy_timeout_ms=10), clock=lambda: now[0])
    with TestClient(app) as client:
        create(client, auth, custom_alias="locked")
        with app.state.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            response = client.get("/locked", follow_redirects=False)
            assert response.status_code == 503
            assert "locked" not in response.text
        assert app.state.store.analytics("locked")["total_clicks"] == 0


def test_rollback_preserves_total(client, auth, app, now):
    create(client, auth, custom_alias="atomic")
    with app.state.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_bucket BEFORE INSERT ON daily_clicks "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        app.state.store.resolve("atomic", now[0])
    assert app.state.store.analytics("atomic")["total_clicks"] == 0


def test_persistence(client, auth, settings):
    create(client, auth, custom_alias="persist")
    with TestClient(create_app(settings)) as second:
        assert second.get("/persist", follow_redirects=False).status_code == 302
        assert (
            second.get("/api/v1/links/persist/analytics", headers=auth).json()["total_clicks"] == 1
        )


def test_body_limits_and_schema(client, auth):
    assert client.post("/api/v1/links", headers=auth, content=b"x" * 8193).status_code == 413
    assert (
        client.post(
            "/api/v1/links", headers=auth, content=iter([b"x" * 5000, b"x" * 5000])
        ).status_code
        == 413
    )
    assert create(client, auth, unexpected="value").status_code == 422
    assert client.post("/api/v1/links", headers=auth, content="{").status_code == 422


def test_creation_limit(settings, auth):
    with TestClient(create_app(replace(settings, create_limit_per_minute=1))) as client:
        assert create(client, auth).status_code == 201
        result = create(client, auth)
        assert result.status_code == 429
        assert result.headers["retry-after"] == "60"
        assert client.get("/health").status_code == 200


def test_health_and_contract(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}
    assert "/api/v1/links" in client.get("/openapi.json").json()["paths"]


def test_configuration_fails_closed():
    with pytest.raises(ValueError):
        Settings(api_key="short")
    with pytest.raises(ValueError):
        Settings(api_key="x" * 32, base_url="https://user:pass@example.com")
    with pytest.raises(ValueError):
        Settings(api_key="x" * 32, create_limit_per_minute=0)


def test_newer_schema_rejected(settings):
    store = Store(settings)
    with store.connection() as db:
        db.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError):
        store.initialize()
