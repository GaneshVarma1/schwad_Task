"""Persistence boundary. Transactions serialize state checks and durable click accounting."""

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config import Settings
from app.models import CreateLink


class DomainError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings

    @contextmanager
    def connection(self):
        db = sqlite3.connect(
            self.settings.database_path, timeout=self.settings.busy_timeout_ms / 1000
        )
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError("Database schema is newer than this application")
            db.execute("PRAGMA journal_mode = WAL")
            if version == 0:
                db.executescript(Path(__file__).with_name("schema.sql").read_text())
            if version < 2:
                db.executescript(Path(__file__).with_name("migration_002.sql").read_text())

    @staticmethod
    def find(db, code):
        row = db.execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
        if row is None:
            raise DomainError(404, "Link not found")
        return dict(row)

    def create(self, data: CreateLink, now: int, idempotency_key: str | None = None):
        expiry = int(data.expires_at.timestamp()) if data.expires_at else None
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest() if idempotency_key else None
        canonical = json.dumps([data.url, data.custom_alias, expiry], separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode()).hexdigest()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if key_hash:
                prior = db.execute(
                    "SELECT request_hash, code FROM idempotency_keys WHERE key_hash = ?",
                    (key_hash,),
                ).fetchone()
                if prior:
                    if prior["request_hash"] != request_hash:
                        raise DomainError(409, "Idempotency key was used with a different request")
                    return self.find(db, prior["code"]), True
            if expiry is not None and expiry <= now:
                raise DomainError(422, "Expiration must be in the future")
            for _ in range(5):
                code = data.custom_alias or secrets.token_urlsafe(6)
                try:
                    db.execute(
                        "INSERT INTO links(code, url, created_at, expires_at) VALUES (?, ?, ?, ?)",
                        (code, data.url, now, expiry),
                    )
                except sqlite3.IntegrityError:
                    if data.custom_alias:
                        raise DomainError(409, "Alias is already in use") from None
                    continue
                if key_hash:
                    db.execute(
                        "INSERT INTO idempotency_keys(key_hash, request_hash, code) "
                        "VALUES (?, ?, ?)",
                        (key_hash, request_hash, code),
                    )
                return self.find(db, code), False
        raise DomainError(503, "Unable to allocate a code; retry later")

    def get(self, code):
        with self.connection() as db:
            return self.find(db, code)

    def disable(self, code):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.find(db, code)
            db.execute("UPDATE links SET disabled = 1 WHERE code = ?", (code,))

    def resolve(self, code, now, count=True):
        with self.connection() as db:
            if count:
                db.execute("BEGIN IMMEDIATE")
            row = self.find(db, code)
            if row["disabled"] or (row["expires_at"] is not None and row["expires_at"] <= now):
                raise DomainError(410, "Link is no longer available")
            if count:
                day = datetime.fromtimestamp(now, UTC).date().isoformat()
                db.execute(
                    "UPDATE links SET total_clicks = total_clicks + 1 WHERE code = ?", (code,)
                )
                db.execute(
                    "INSERT INTO daily_clicks(code, day, clicks) VALUES (?, ?, 1) "
                    "ON CONFLICT(code, day) DO UPDATE SET clicks = clicks + 1",
                    (code, day),
                )
            return row["url"]

    def analytics(self, code):
        with self.connection() as db:
            db.execute("BEGIN")  # One read snapshot for total and buckets.
            row = self.find(db, code)
            daily = db.execute(
                "SELECT day AS date, clicks FROM daily_clicks WHERE code = ? ORDER BY day", (code,)
            ).fetchall()
            return {
                "code": code,
                "total_clicks": row["total_clicks"],
                "daily": [dict(item) for item in daily],
            }

    def list_links(self, now, query="", status="all", limit=10, offset=0):
        count_sql = """SELECT COUNT(*) FROM links
                   WHERE (? = '' OR instr(lower(code), lower(?)) > 0
                   OR instr(lower(url), lower(?)) > 0)
                   AND (? = 'all'
                     OR (? = 'active' AND disabled = 0 AND (expires_at IS NULL OR expires_at > ?))
                     OR (? = 'disabled' AND disabled = 1)
                     OR (? = 'expired' AND disabled = 0 AND expires_at <= ?))"""
        page_sql = """SELECT * FROM links
                   WHERE (? = '' OR instr(lower(code), lower(?)) > 0
                   OR instr(lower(url), lower(?)) > 0)
                   AND (? = 'all'
                     OR (? = 'active' AND disabled = 0 AND (expires_at IS NULL OR expires_at > ?))
                     OR (? = 'disabled' AND disabled = 1)
                     OR (? = 'expired' AND disabled = 0 AND expires_at <= ?))
                   ORDER BY created_at DESC, code LIMIT ? OFFSET ?"""
        params = (query, query, query, status, status, now, status, status, now)
        with self.connection() as db:
            db.execute("BEGIN")
            total = db.execute(count_sql, params).fetchone()[0]
            rows = db.execute(page_sql, (*params, limit, offset)).fetchall()
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def dashboard(self, now, days=30):
        today = datetime.fromtimestamp(now, UTC).date()
        start = today - timedelta(days=days - 1)
        with self.connection() as db:
            db.execute("BEGIN")
            totals = db.execute(
                "SELECT COUNT(*) AS total_links, COALESCE(SUM(total_clicks), 0) AS total_clicks, "
                "COALESCE(SUM(CASE WHEN disabled = 0 AND "
                "(expires_at IS NULL OR expires_at > ?) THEN 1 ELSE 0 END), 0) AS active_links "
                "FROM links",
                (now,),
            ).fetchone()
            buckets = db.execute(
                "SELECT day, SUM(clicks) AS clicks FROM daily_clicks "
                "WHERE day >= ? AND day <= ? GROUP BY day ORDER BY day",
                (start.isoformat(), today.isoformat()),
            ).fetchall()
            counts = {row["day"]: row["clicks"] for row in buckets}
            daily = [
                {
                    "date": (start + timedelta(days=i)).isoformat(),
                    "clicks": counts.get((start + timedelta(days=i)).isoformat(), 0),
                }
                for i in range(days)
            ]
            top = db.execute(
                "SELECT * FROM links ORDER BY total_clicks DESC, code LIMIT 5"
            ).fetchall()
            return {
                **dict(totals),
                "clicks_today": counts.get(today.isoformat(), 0),
                "daily": daily,
                "top_links": [dict(row) for row in top],
            }
