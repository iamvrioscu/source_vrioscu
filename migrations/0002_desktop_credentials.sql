-- VRIOSCU desktop API credentials.
-- Store only a SHA-256 hash of the raw random credential.
-- Never store the credential itself.

CREATE TABLE desktop_credentials (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL UNIQUE
                 REFERENCES users(id) ON DELETE CASCADE,
    token_hash   TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at   TEXT
);

CREATE INDEX idx_desktop_credentials_user
    ON desktop_credentials(user_id);
