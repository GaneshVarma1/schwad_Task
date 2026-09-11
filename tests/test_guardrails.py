import asyncio
import logging
from unittest.mock import patch

import pytest

from app.main import BodyLimit, CreateLimiter
from app.store import DomainError


def test_stream_limit_and_empty_frames():
    async def scenario(chunks, expected):
        incoming = iter(chunks)
        outgoing = []
        observed = []

        async def receive():
            return next(incoming, {"type": "http.disconnect"})

        async def send(message):
            outgoing.append(message)

        async def downstream(scope, receive, send):
            observed.append(await receive())

        await BodyLimit(downstream, limit=4)({"type": "http"}, receive, send)
        if expected == 413:
            assert outgoing[0]["status"] == 413
            assert not observed
        elif expected is None:
            assert not observed
        else:
            assert observed == [{"type": "http.request", "body": expected, "more_body": False}]

    def frame(body, more):
        return {"type": "http.request", "body": body, "more_body": more}

    asyncio.run(scenario([frame(b"", True)] * 10000 + [frame(b"test", False)], b"test"))
    asyncio.run(scenario([frame(b"abc", True), frame(b"de", False)], 413))
    asyncio.run(scenario([{"type": "http.disconnect"}], None))


def test_limiter_window_recovers():
    limiter = CreateLimiter(1)
    with patch("app.main.time.monotonic", return_value=0):
        limiter.admit()
        with pytest.raises(DomainError) as error:
            limiter.admit()
        assert error.value.status == 429
    with patch("app.main.time.monotonic", return_value=60):
        limiter.admit()
    assert len(limiter.events) == 1


def test_wrong_auth_and_host_injection(client, auth):
    response = client.post(
        "/api/v1/links",
        headers={"Authorization": "Bearer wrong"},
        json={"url": "https://example.com"},
    )
    assert response.status_code == 401
    result = client.post(
        "/api/v1/links",
        headers={**auth, "Host": "evil.example"},
        json={"url": "https://example.com"},
    )
    assert result.json()["short_url"].startswith("http://127.0.0.1:8000/")


def test_application_logs_do_not_include_sensitive_fields(client, auth, caplog):
    caplog.set_level(logging.INFO, logger="shortener")
    client.post(
        "/api/v1/links",
        headers=auth,
        json={"url": "https://example.com/secret?q=private", "custom_alias": "privatealias"},
    )
    client.get(
        "/privatealias",
        headers={"User-Agent": "private-agent", "Referer": "https://secret.example/"},
        follow_redirects=False,
    )
    messages = " ".join(
        record.getMessage() for record in caplog.records if record.name == "shortener"
    )
    for forbidden in ["private", "secret", auth["Authorization"]]:
        assert forbidden not in messages
    assert "route=/{code}" in messages
    assert "status=302" in messages
