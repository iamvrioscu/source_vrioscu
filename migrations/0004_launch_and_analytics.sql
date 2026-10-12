-- Additive migration; all timestamps retain the existing UTC storage convention.
CREATE TABLE launch_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    visible INTEGER NOT NULL DEFAULT 1 CHECK (visible IN (0,1)),
    registrations_enabled INTEGER NOT NULL DEFAULT 1 CHECK (registrations_enabled IN (0,1)),
    heading TEXT NOT NULL,
    description TEXT NOT NULL,
    button_label TEXT NOT NULL,
    success_message TEXT NOT NULL,
    updated_at TEXT
);
INSERT INTO launch_settings(id, heading, description, button_label, success_message) VALUES
(1, 'Be among the first to experience VRIOSCU.', 'Get notified when the Windows application becomes available. Join the launch list for release news.', 'Join the launch list', 'Your launch interest has been saved. No email has been sent.');
CREATE TABLE launch_subscribers (
    id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    status TEXT NOT NULL DEFAULT 'registered' CHECK (status IN ('registered','unsubscribed')),
    consent_granted INTEGER NOT NULL CHECK (consent_granted IN (0,1)),
    notice_version TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmed_at TEXT
);
CREATE INDEX idx_launch_registered ON launch_subscribers(registered_at, id);
CREATE INDEX idx_launch_status ON launch_subscribers(status, registered_at);
CREATE TABLE analytics_visitors (
    id TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX idx_analytics_active ON analytics_visitors(last_seen_at);
CREATE TABLE analytics_visits (
    id INTEGER PRIMARY KEY,
    visitor_id TEXT NOT NULL REFERENCES analytics_visitors(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    referrer TEXT NOT NULL,
    browser TEXT NOT NULL,
    device TEXT NOT NULL
);
CREATE INDEX idx_visits_visitor ON analytics_visits(visitor_id, last_seen_at);
CREATE INDEX idx_visits_started ON analytics_visits(started_at);
CREATE INDEX idx_visits_activity ON analytics_visits(last_seen_at);
CREATE TABLE analytics_views (
    id INTEGER PRIMARY KEY,
    visit_id INTEGER NOT NULL REFERENCES analytics_visits(id) ON DELETE CASCADE,
    visitor_id TEXT NOT NULL REFERENCES analytics_visitors(id) ON DELETE CASCADE,
    event_id TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(visitor_id, event_id)
);
CREATE INDEX idx_views_created ON analytics_views(created_at, path);
CREATE INDEX idx_views_visitor ON analytics_views(visitor_id, created_at);
CREATE INDEX idx_views_visit ON analytics_views(visit_id);
CREATE TABLE analytics_maintenance (id INTEGER PRIMARY KEY CHECK(id = 1), cleaned_at TEXT NOT NULL);
