"""Explicit configuration; no working production credentials or proxy-header trust."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    api_key: str
    database_path: str = "shortener.db"
    base_url: str = "http://127.0.0.1:8000"
    busy_timeout_ms: int = 1000
    create_limit_per_minute: int = 60
    demo_mode: bool = False  # Only enabled by the isolated local demo launcher.

    def __post_init__(self):
        if len(self.api_key.encode()) < 32:
            raise ValueError("SHORTENER_API_KEY must contain at least 32 bytes")
        parts = urlsplit(self.base_url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/"}
        ):
            raise ValueError("SHORTENER_BASE_URL must be an absolute HTTP(S) origin")
        if self.busy_timeout_ms < 1 or self.create_limit_per_minute < 1:
            raise ValueError("Timeout and create limit must be positive")

    @classmethod
    def from_env(cls):
        return cls(
            api_key=os.environ.get("SHORTENER_API_KEY", ""),
            database_path=os.environ.get("SHORTENER_DATABASE", "shortener.db"),
            base_url=os.environ.get("SHORTENER_BASE_URL", "http://127.0.0.1:8000"),
        )
