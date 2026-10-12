-- SQLite requires a table copy to relax the checksum constraint. Preserve every
-- release, its ID, original checksum, timestamps and related download counts.
CREATE TABLE releases_next (
    id                         INTEGER PRIMARY KEY,
    version                    TEXT NOT NULL,
    channel                    TEXT NOT NULL CHECK (channel IN ('PUBLIC_BETA', 'STABLE', 'INTERNAL', 'DEV')),
    release_date               TEXT NOT NULL,
    release_notes_url          TEXT NOT NULL DEFAULT '',
    download_url               TEXT NOT NULL,
    installer_filename         TEXT NOT NULL,
    sha256                     TEXT CHECK (sha256 IS NULL OR length(sha256) = 64),
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
INSERT INTO releases_next SELECT * FROM releases;

-- Copy the sole referencing table before swapping the parent, so ON DELETE
-- CASCADE cannot discard historical download statistics. The migration runner
-- wraps this complete operation in one transaction with foreign keys enabled.
CREATE TABLE download_stats_next (
    release_id INTEGER NOT NULL REFERENCES releases_next(id) ON DELETE CASCADE,
    day        TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (release_id, day)
);
INSERT INTO download_stats_next SELECT * FROM download_stats;
DROP TABLE download_stats;
DROP TABLE releases;
ALTER TABLE releases_next RENAME TO releases;
ALTER TABLE download_stats_next RENAME TO download_stats;
CREATE INDEX idx_releases_channel ON releases(channel, is_published, release_date);
