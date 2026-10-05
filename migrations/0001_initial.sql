-- VRIOSCU website schema v1
-- Timestamps are ISO-8601 UTC strings: YYYY-MM-DDTHH:MM:SSZ

CREATE TABLE users (
    id                  INTEGER PRIMARY KEY,
    username            TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email               TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash       TEXT NOT NULL,
    first_name          TEXT NOT NULL DEFAULT '',
    last_name           TEXT NOT NULL DEFAULT '',
    country             TEXT NOT NULL DEFAULT '',
    purpose             TEXT NOT NULL DEFAULT '',
    role                TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    failed_login_count  INTEGER NOT NULL DEFAULT 0,
    locked_until        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    last_login_at       TEXT,
    password_changed_at TEXT NOT NULL
);

-- Server-side sessions. The cookie carries a random token; only its
-- SHA-256 is stored, so a database leak does not yield live sessions.
CREATE TABLE sessions (
    id            INTEGER PRIMARY KEY,
    token_hash    TEXT NOT NULL UNIQUE,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_secret   TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    revoked_at    TEXT
);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

-- Optional product-update subscription, separate from the account.
CREATE TABLE product_update_preferences (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    opted_in    INTEGER NOT NULL DEFAULT 0 CHECK (opted_in IN (0, 1)),
    updated_at  TEXT NOT NULL
);

-- Append-only history of notice acknowledgements and opt-in changes.
CREATE TABLE consent_records (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose         TEXT NOT NULL CHECK (purpose IN ('privacy_notice', 'product_updates')),
    granted         INTEGER NOT NULL CHECK (granted IN (0, 1)),
    notice_version  TEXT NOT NULL,
    recorded_at     TEXT NOT NULL
);
CREATE INDEX idx_consent_user ON consent_records(user_id);

CREATE TABLE feedback (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category     TEXT NOT NULL CHECK (category IN ('bug', 'usability', 'report', 'feature', 'other')),
    app_version  TEXT NOT NULL DEFAULT '',
    message      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewed', 'closed')),
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_feedback_created ON feedback(created_at);

CREATE TABLE support_requests (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    topic       TEXT NOT NULL CHECK (topic IN ('installation', 'account', 'reports', 'privacy', 'general')),
    message     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'in_progress', 'closed')),
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_support_created ON support_requests(created_at);

CREATE TABLE releases (
    id                         INTEGER PRIMARY KEY,
    version                    TEXT NOT NULL,
    channel                    TEXT NOT NULL CHECK (channel IN ('PUBLIC_BETA', 'STABLE', 'INTERNAL', 'DEV')),
    release_date               TEXT NOT NULL,
    release_notes_url          TEXT NOT NULL DEFAULT '',
    download_url               TEXT NOT NULL,
    installer_filename         TEXT NOT NULL,
    sha256                     TEXT NOT NULL CHECK (length(sha256) = 64),
    file_size_bytes            INTEGER NOT NULL CHECK (file_size_bytes > 0),
    is_mandatory               INTEGER NOT NULL DEFAULT 0 CHECK (is_mandatory IN (0, 1)),
    minimum_supported_version  TEXT NOT NULL DEFAULT '',
    is_signed                  INTEGER NOT NULL DEFAULT 0 CHECK (is_signed IN (0, 1)),
    is_published               INTEGER NOT NULL DEFAULT 0 CHECK (is_published IN (0, 1)),
    created_by                 INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at                 TEXT NOT NULL,
    updated_at                 TEXT NOT NULL,
    UNIQUE (version, channel)
);
CREATE INDEX idx_releases_channel ON releases(channel, is_published, release_date);

-- Aggregate download counts only. No IP addresses or identifiers.
CREATE TABLE download_stats (
    release_id  INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    day         TEXT NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (release_id, day)
);

-- Rate-limit buckets. Keys are HMAC digests, never raw IPs or emails.
CREATE TABLE rate_limits (
    bucket        TEXT PRIMARY KEY,
    window_start  INTEGER NOT NULL,
    count         INTEGER NOT NULL
);

CREATE TABLE audit_log (
    id             INTEGER PRIMARY KEY,
    actor_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action         TEXT NOT NULL,
    target         TEXT NOT NULL DEFAULT '',
    detail         TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL
);
CREATE INDEX idx_audit_created ON audit_log(created_at);
