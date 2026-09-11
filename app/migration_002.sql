BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key_hash TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    code TEXT NOT NULL REFERENCES links(code)
);
PRAGMA user_version = 2;
COMMIT;
