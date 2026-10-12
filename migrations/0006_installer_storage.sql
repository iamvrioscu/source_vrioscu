-- Additive migration: existing release IDs, metadata and download counts remain intact.
ALTER TABLE releases ADD COLUMN storage_key TEXT;
ALTER TABLE releases ADD COLUMN uploaded_at TEXT;
CREATE UNIQUE INDEX idx_release_storage ON releases(storage_key) WHERE storage_key IS NOT NULL;

-- Uploads are temporary transfer state, not a second release catalog.
CREATE TABLE release_uploads (
    id TEXT PRIMARY KEY,
    owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    original_filename TEXT NOT NULL,
    expected_bytes INTEGER NOT NULL CHECK(expected_bytes > 0),
    received_bytes INTEGER NOT NULL DEFAULT 0 CHECK(received_bytes >= 0),
    state TEXT NOT NULL DEFAULT 'uploading' CHECK(state IN ('uploading','verified','attached','cancelled')),
    sha256 TEXT,
    storage_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    release_id INTEGER REFERENCES releases(id) ON DELETE SET NULL
);
CREATE INDEX idx_upload_expiry ON release_uploads(state, expires_at);
