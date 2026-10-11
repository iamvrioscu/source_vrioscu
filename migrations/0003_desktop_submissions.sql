-- Desktop-originated feedback, bug reports, problem reports, and feature requests.
-- Client IDs are scoped to a user so retries cannot create duplicate submissions.
CREATE TABLE desktop_submissions (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_submission_id TEXT NOT NULL,
    submission_type     TEXT NOT NULL CHECK (
        submission_type IN ('feedback', 'bug_report', 'problem_report', 'feature_request')
    ),
    details_json        TEXT NOT NULL,
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    app_version         TEXT NOT NULL DEFAULT '',
    client_created_at   TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new', 'reviewed', 'closed')),
    created_at          TEXT NOT NULL,
    UNIQUE (user_id, client_submission_id)
);

CREATE INDEX idx_desktop_submissions_created
    ON desktop_submissions(created_at, id);
CREATE INDEX idx_desktop_submissions_status
    ON desktop_submissions(status, created_at, id);
CREATE INDEX idx_desktop_submissions_user
    ON desktop_submissions(user_id, created_at, id);
