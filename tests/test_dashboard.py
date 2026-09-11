from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.demo import seed_demo
from app.main import create_app


def test_dashboard_shell_and_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Schwab Link Manager" in response.text
    assert "Interview prototype" in response.text
    assert "Content-Security-Policy" in response.headers
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    for path in ["dashboard.css", "dashboard.js", "dashboard-core.mjs", "favicon.svg"]:
        response = client.get(f"/ui/assets/{path}")
        assert response.status_code == 200
    assert client.get("/api/v1/ui-config").json() == {
        "demo": False,
        "base_url": "http://127.0.0.1:8000",
    }


@pytest.mark.parametrize("path", ["/api/v1/links", "/api/v1/dashboard"])
def test_dashboard_management_requires_auth(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_link_listing_search_status_and_pagination(client, auth, now):
    def create(code, **extra):
        response = client.post(
            "/api/v1/links",
            headers=auth,
            json={"url": f"https://example.com/{code}", "custom_alias": code, **extra},
        )
        assert response.status_code == 201

    create("alpha")
    now[0] += 1
    create("beta")
    now[0] += 1
    create("gamma", expires_at=datetime.fromtimestamp(now[0] + 1, UTC).isoformat())
    now[0] += 1
    create("delta")
    now[0] += 1
    client.delete("/api/v1/links/beta", headers=auth)
    client.get("/alpha", follow_redirects=False)
    page = client.get("/api/v1/links?limit=2", headers=auth).json()
    assert page["total"] == 4
    assert [row["code"] for row in page["items"]] == ["delta", "gamma"]
    page = client.get("/api/v1/links?limit=2&offset=2", headers=auth).json()
    assert [row["code"] for row in page["items"]] == ["beta", "alpha"]
    assert page["items"][1]["total_clicks"] == 1
    for status, expected in [
        ("active", ["delta", "alpha"]),
        ("disabled", ["beta"]),
        ("expired", ["gamma"]),
    ]:
        page = client.get(f"/api/v1/links?status={status}", headers=auth).json()
        assert [row["code"] for row in page["items"]] == expected
        assert all(row["status"] == status for row in page["items"])
    page = client.get("/api/v1/links?q=ALPHA", headers=auth).json()
    assert page["total"] == 1
    assert page["items"][0]["code"] == "alpha"
    assert client.get("/api/v1/links?q=example.com", headers=auth).json()["total"] == 4
    assert client.get("/api/v1/links?q=%25", headers=auth).json()["total"] == 0
    assert (
        client.get("/api/v1/links", params={"q": "' OR 1=1 --"}, headers=auth).json()["total"] == 0
    )
    assert client.get("/api/v1/links?offset=900", headers=auth).json()["items"] == []


def test_summary_fills_empty_days_and_counts_all_links(client, auth, now):
    empty = client.get("/api/v1/dashboard?days=7", headers=auth).json()
    assert empty["total_links"] == empty["active_links"] == empty["total_clicks"] == 0
    assert len(empty["daily"]) == 7
    assert all(row["clicks"] == 0 for row in empty["daily"])
    client.post(
        "/api/v1/links", headers=auth, json={"url": "https://example.com", "custom_alias": "daily"}
    )
    client.get("/daily", follow_redirects=False)
    now[0] += 86400
    client.get("/daily", follow_redirects=False)
    client.get("/daily", follow_redirects=False)
    client.delete("/api/v1/links/daily", headers=auth)
    result = client.get("/api/v1/dashboard?days=7", headers=auth).json()
    assert result["total_links"] == 1
    assert result["active_links"] == 0
    assert result["total_clicks"] == 3
    assert result["clicks_today"] == 2
    assert result["daily"][-1]["clicks"] == 2
    assert result["daily"][-2]["clicks"] == 1
    assert result["top_links"][0]["code"] == "daily"
    assert result["top_links"][0]["status"] == "disabled"
    assert (
        client.get("/api/v1/dashboard?days=1", headers=auth).json()["daily"] == result["daily"][-1:]
    )


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=101", "offset=-1", "offset=1000001", "status=invalid", "q=" + "x" * 201],
)
def test_listing_input_is_bounded(client, auth, query):
    assert client.get(f"/api/v1/links?{query}", headers=auth).status_code == 422


@pytest.mark.parametrize("days", [0, 91, -1, "bad"])
def test_chart_range_is_bounded(client, auth, days):
    assert client.get(f"/api/v1/dashboard?days={days}", headers=auth).status_code == 422


def test_isolated_demo_and_cross_origin_guard(settings, now):
    app = create_app(replace(settings, demo_mode=True), clock=lambda: now[0])
    with TestClient(app) as demo:
        seed_demo(app.state.store, now[0])
        assert demo.get("/api/v1/ui-config").json()["demo"] is True
        summary = demo.get("/api/v1/dashboard").json()
        assert summary["total_links"] == 12
        assert summary["active_links"] == 9
        assert sum(row["clicks"] for row in summary["daily"]) == summary["total_clicks"]
        assert (
            demo.get("/api/v1/dashboard", headers={"Origin": "https://evil.example"}).status_code
            == 403
        )
        assert (
            demo.get("/api/v1/dashboard", headers={"Origin": settings.base_url}).status_code == 200
        )
        assert (
            demo.get("/api/v1/dashboard", headers={"Origin": "https://testserver"}).status_code
            == 200
        )
        result = demo.post(
            "/api/v1/links", json={"url": "https://example.com", "custom_alias": "ui-demo"}
        )
        assert result.status_code == 201
        assert demo.get("/ui-demo", follow_redirects=False).status_code == 302
        assert demo.delete("/api/v1/links/ui-demo").status_code == 204
        assert demo.get("/ui-demo").status_code == 410


def test_regular_startup_cannot_enable_demo_from_environment(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("SHORTENER_API_KEY", "test-key-with-at-least-thirty-two-bytes")
    monkeypatch.setenv("SHORTENER_DEMO", "true")
    assert Settings.from_env().demo_mode is False


def test_dashboard_assets_do_not_shadow_existing_short_codes(client, auth):
    response = client.post(
        "/api/v1/links", headers=auth, json={"url": "https://example.com", "custom_alias": "assets"}
    )
    assert response.status_code == 201
    assert client.get("/assets", follow_redirects=False).status_code == 302
    assert client.get("/ui/assets/dashboard.js").status_code == 200
