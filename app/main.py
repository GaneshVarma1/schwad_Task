"""HTTP transport, admission controls, and composition root."""

import logging
import secrets
import sqlite3
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path as FilePath
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.models import (
    CODE_PATTERN,
    Analytics,
    CreateLink,
    DashboardSummary,
    ErrorResponse,
    Link,
    LinkPage,
    ManagedLink,
)
from app.store import DomainError, Store

logger = logging.getLogger("shortener")
Code = Annotated[str, Path(pattern=CODE_PATTERN)]


def errors(*statuses):
    return {status: {"model": ErrorResponse} for status in statuses}


class BodyLimit:
    """Bound streamed bodies before JSON parsing, including requests without Content-Length."""

    def __init__(self, app, limit=8192):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.limit:
                response = JSONResponse({"detail": "Request body too large"}, status_code=413)
                return await response(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        pending = True

        async def replay():
            nonlocal pending
            if pending:
                pending = False
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


class CreateLimiter:
    """Bounded single-process admission budget. Shared gateway limiting is a deployment gate."""

    def __init__(self, limit):
        self.limit, self.events, self.lock = limit, deque(), threading.Lock()

    def admit(self):
        with self.lock:
            now = time.monotonic()
            while self.events and self.events[0] <= now - 60:
                self.events.popleft()
            if len(self.events) >= self.limit:
                raise DomainError(429, "Creation budget exceeded; retry later")
            self.events.append(now)


def create_app(settings: Settings | None = None, clock=time.time):
    settings = settings or Settings.from_env()
    store = Store(settings)
    limiter = CreateLimiter(settings.create_limit_per_minute)

    @asynccontextmanager
    async def lifespan(app):
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        store.initialize()
        yield

    app = FastAPI(title="Engineer-led URL Shortener", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(BodyLimit)
    security = HTTPBearer(auto_error=False)

    def authenticate(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    ):
        if settings.demo_mode:
            return  # Isolated sample DB, local-only launcher; never used by from_env().
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode(), settings.api_key.encode()
        ):
            raise DomainError(401, "Valid bearer token required")

    auth = [Depends(authenticate)]

    @app.middleware("http")
    async def observability(request: Request, call_next):
        request_id = uuid.uuid4().hex
        start = time.monotonic()
        origin = request.headers.get("origin")
        same_host_demo_origin = origin is not None and (
            urlsplit(origin).scheme in {"http", "https"}
            and urlsplit(origin).netloc == request.headers.get("host")
        )
        if (
            settings.demo_mode
            and origin not in {None, settings.base_url.rstrip("/")}
            and not same_host_demo_origin
        ):
            response = JSONResponse({"detail": "Cross-origin demo requests are forbidden"}, 403)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path == "/" or request.url.path.startswith("/ui/assets/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
                "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            )
        # No URL, query, IP, authorization, referrer, or user-agent in application logs.
        route = request.scope.get("route")
        logger.info(
            "request_id=%s method=%s route=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            getattr(route, "path", "unmatched"),
            response.status_code,
            (time.monotonic() - start) * 1000,
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        headers = {}
        if exc.status in {429, 503}:
            headers["Retry-After"] = "60" if exc.status == 429 else "1"
        if exc.status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse({"detail": exc.message}, exc.status, headers=headers)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_error(request, exc):
        logger.error("database_unavailable error_type=%s", type(exc).__name__)
        return JSONResponse(
            {"detail": "Storage temporarily unavailable"}, 503, headers={"Retry-After": "1"}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic errors may contain submitted URLs or secrets; do not echo input.
        return JSONResponse(
            {
                "detail": "Invalid request",
                "errors": [{"field": list(e["loc"]), "type": e["type"]} for e in exc.errors()],
            },
            422,
        )

    def public_link(row):
        return Link(
            code=row["code"],
            url=row["url"],
            short_url=f"{settings.base_url.rstrip('/')}/{row['code']}",
            created_at=datetime.fromtimestamp(row["created_at"], UTC),
            expires_at=datetime.fromtimestamp(row["expires_at"], UTC)
            if row["expires_at"] is not None
            else None,
            disabled=bool(row["disabled"]),
        )

    def managed_link(row):
        status = (
            "disabled"
            if row["disabled"]
            else (
                "expired"
                if row["expires_at"] is not None and row["expires_at"] <= int(clock())
                else "active"
            )
        )
        return ManagedLink(
            **public_link(row).model_dump(), total_clicks=row["total_clicks"], status=status
        )

    static_dir = FilePath(__file__).with_name("static")
    app.mount("/ui/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard_page():
        return FileResponse(static_dir / "index.html")

    @app.get("/api/v1/ui-config", tags=["dashboard"])
    def ui_config():
        return {"demo": settings.demo_mode, "base_url": settings.base_url}

    @app.get(
        "/api/v1/links",
        response_model=LinkPage,
        dependencies=auth,
        responses=errors(401, 422, 503),
        tags=["management"],
    )
    def list_links(
        q: Annotated[str, Query(max_length=200)] = "",
        status: Literal["all", "active", "disabled", "expired"] = "all",
        limit: Annotated[int, Query(ge=1, le=100)] = 10,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
    ):
        page = store.list_links(int(clock()), q, status, limit, offset)
        page["items"] = [managed_link(row) for row in page["items"]]
        return page

    @app.get(
        "/api/v1/dashboard",
        response_model=DashboardSummary,
        dependencies=auth,
        responses=errors(401, 422, 503),
        tags=["dashboard"],
    )
    def dashboard(days: Annotated[int, Query(ge=1, le=90)] = 30):
        summary = store.dashboard(int(clock()), days)
        summary["top_links"] = [managed_link(row) for row in summary["top_links"]]
        return summary

    @app.get("/health", tags=["operations"])
    def health():
        return {"status": "ok"}

    @app.get("/ready", tags=["operations"])
    def ready():
        with store.connection() as db:
            db.execute("SELECT code FROM links LIMIT 1").fetchall()
        return {"status": "ready"}

    @app.post(
        "/api/v1/links",
        response_model=Link,
        status_code=201,
        responses={
            200: {"model": Link, "description": "Idempotent replay"},
            **errors(401, 409, 413, 422, 429, 503),
        },
        dependencies=auth,
        tags=["management"],
    )
    def create(
        data: CreateLink,
        response: Response,
        idempotency_key: Annotated[
            str | None, Header(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
        ] = None,
    ):
        limiter.admit()
        row, replayed = store.create(data, int(clock()), idempotency_key)
        response.status_code = 200 if replayed else 201
        response.headers["Idempotency-Replayed"] = str(replayed).lower()
        response.headers["Location"] = f"/api/v1/links/{row['code']}"
        return public_link(row)

    @app.get(
        "/api/v1/links/{code}",
        response_model=Link,
        dependencies=auth,
        responses=errors(401, 404, 422, 503),
        tags=["management"],
    )
    def get(code: Code):
        return public_link(store.get(code))

    @app.delete(
        "/api/v1/links/{code}",
        status_code=204,
        dependencies=auth,
        responses=errors(401, 404, 422, 503),
        tags=["management"],
    )
    def disable(code: Code):
        store.disable(code)
        return Response(status_code=204)

    @app.get(
        "/api/v1/links/{code}/analytics",
        response_model=Analytics,
        responses=errors(401, 404, 422, 503),
        dependencies=auth,
        tags=["management"],
    )
    def analytics(code: Code):
        return store.analytics(code)

    @app.get(
        "/{code}",
        status_code=302,
        response_class=RedirectResponse,
        responses=errors(404, 410, 422, 503),
        tags=["redirects"],
        operation_id="resolveLink",
    )
    @app.head(
        "/{code}",
        status_code=302,
        response_class=RedirectResponse,
        responses=errors(404, 410, 422, 503),
        tags=["redirects"],
        operation_id="inspectLink",
    )
    def redirect(code: Code, request: Request):
        return RedirectResponse(store.resolve(code, int(clock()), request.method == "GET"), 302)

    return app
