"""Request validation and public API contracts."""

import ipaddress
import re
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

CODE_PATTERN = r"^[A-Za-z0-9_-]{4,32}$"
RESERVED = {"health", "ready", "docs", "redoc", "openapi", "api"}


class CreateLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    custom_alias: str | None = Field(default=None, pattern=CODE_PATTERN)
    expires_at: datetime | None = None

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        # Reject ambiguous browser/parser inputs; never fetch the destination.
        if any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
            raise ValueError("Whitespace, control characters and backslashes are forbidden")
        if re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f)", value, re.IGNORECASE):
            raise ValueError("Encoded control characters are forbidden")
        try:
            parsed = urlsplit(value)
            host = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Invalid URL") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or port == 0
        ):
            raise ValueError("An HTTP(S) URL without credentials is required")
        host = host.rstrip(".").lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            try:
                ascii_host = host.encode("idna").decode("ascii")
            except UnicodeError as exc:
                raise ValueError("Invalid hostname") from exc
            labels = ascii_host.split(".")
            if (
                len(ascii_host) > 253
                or len(labels) < 2
                or labels[-1].isdigit()
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels)
                or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid"))
            ):
                raise ValueError("A public-looking hostname is required") from None
        else:
            if not address.is_global:
                raise ValueError("Non-public IP literals are forbidden")
        return value

    @field_validator("custom_alias")
    @classmethod
    def nonreserved_alias(cls, value: str | None) -> str | None:
        if value and value.lower() in RESERVED:
            raise ValueError("Reserved alias")
        return value

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime | None) -> datetime | None:
        if value and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Expiration must include a timezone")
        return value


class Link(BaseModel):
    code: str
    url: str
    short_url: str
    created_at: datetime
    expires_at: datetime | None
    disabled: bool


class DailyClicks(BaseModel):
    date: str
    clicks: int


class Analytics(BaseModel):
    code: str
    total_clicks: int
    daily: list[DailyClicks]
    definition: str = "Committed GET redirect decisions; includes bots and repeat requests"


class ErrorResponse(BaseModel):
    detail: str
    errors: list[dict[str, object]] | None = None


class ManagedLink(Link):
    total_clicks: int
    status: str


class LinkPage(BaseModel):
    items: list[ManagedLink]
    total: int
    limit: int
    offset: int


class DashboardSummary(BaseModel):
    total_links: int
    active_links: int
    total_clicks: int
    clicks_today: int
    daily: list[DailyClicks]
    top_links: list[ManagedLink]
