from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import CreateLink
from app.store import Store


def test_replay_and_conflict(client, auth, app):
    headers = {**auth, "Idempotency-Key": "retry-key-123"}
    original = client.post("/api/v1/links", headers=headers, json={"url": "https://example.com"})
    retry = client.post("/api/v1/links", headers=headers, json={"url": "https://example.com"})
    assert original.status_code == 201
    assert retry.status_code == 200
    assert original.json() == retry.json()
    assert retry.headers["idempotency-replayed"] == "true"
    conflict = client.post("/api/v1/links", headers=headers, json={"url": "https://example.org"})
    assert conflict.status_code == 409
    with app.state.store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 1
        assert db.execute("SELECT key_hash FROM idempotency_keys").fetchone()[0] != "retry-key-123"


def test_concurrent_retries_create_one_link(client, app, now):
    data = CreateLink(url="https://example.com")
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(
            pool.map(lambda _: app.state.store.create(data, now[0], "parallel-key"), range(24))
        )
    assert len({row["code"] for row, _ in results}) == 1
    assert sum(not replayed for _, replayed in results) == 1


def test_expired_replay_and_disable_do_not_reactivate(client, app, auth, now):
    headers = {**auth, "Idempotency-Key": "expires-key"}
    payload = {
        "url": "https://example.com",
        "expires_at": datetime.fromtimestamp(now[0] + 1, UTC).isoformat(),
    }
    code = client.post("/api/v1/links", headers=headers, json=payload).json()["code"]
    now[0] += 1
    assert client.post("/api/v1/links", headers=headers, json=payload).status_code == 200
    assert client.get(f"/{code}").status_code == 410
    client.delete(f"/api/v1/links/{code}", headers=auth)
    replay = client.post("/api/v1/links", headers=headers, json=payload)
    assert replay.json()["disabled"] is True
    assert client.get(f"/{code}").status_code == 410


def test_key_validation(client, auth):
    for key in ["short", "x" * 129, "space in key"]:
        response = client.post(
            "/api/v1/links",
            headers={**auth, "Idempotency-Key": key},
            json={"url": "https://example.com"},
        )
        assert response.status_code == 422


def test_failed_request_does_not_reserve_key(client, auth):
    headers = {**auth, "Idempotency-Key": "failure-key"}
    assert (
        client.post(
            "/api/v1/links",
            headers=headers,
            json={"url": "https://example.com", "expires_at": "2000-01-01T00:00:00Z"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/links", headers=headers, json={"url": "https://example.com"}
        ).status_code
        == 201
    )


def test_v1_migration_preserves_links_and_analytics(settings, auth):
    store = Store(settings)
    with store.connection() as db:
        db.executescript(Path("app/schema.sql").read_text())
        db.execute(
            "INSERT INTO links(code,url,created_at,total_clicks) VALUES (?,?,?,?)",
            ("legacy", "https://example.com", 1700000000, 7),
        )
        db.execute("INSERT INTO daily_clicks VALUES (?,?,?)", ("legacy", "2023-11-14", 7))
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            assert (
                client.get("/api/v1/links/legacy/analytics", headers=auth).json()["total_clicks"]
                == 7
            )
            with store.connection() as db:
                assert db.execute("PRAGMA user_version").fetchone()[0] == 2
                assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_replay_survives_restart(settings, auth):
    headers = {**auth, "Idempotency-Key": "restart-key"}
    with TestClient(create_app(settings)) as client:
        first = client.post("/api/v1/links", headers=headers, json={"url": "https://example.com"})
    with TestClient(create_app(settings)) as client:
        retry = client.post("/api/v1/links", headers=headers, json={"url": "https://example.com"})
        assert retry.status_code == 200
        assert first.json() == retry.json()
