CREATE TABLE IF NOT EXISTS links (
    code TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER,
    disabled INTEGER NOT NULL DEFAULT 0 CHECK (disabled IN (0, 1)),
    total_clicks INTEGER NOT NULL DEFAULT 0 CHECK (total_clicks >= 0)
);
CREATE TABLE IF NOT EXISTS daily_clicks (
    code TEXT NOT NULL REFERENCES links(code),
    day TEXT NOT NULL,
    clicks INTEGER NOT NULL CHECK (clicks > 0),
    PRIMARY KEY (code, day)
);
PRAGMA user_version = 1;
