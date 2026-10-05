# Database

SQLite 3 in WAL mode, `foreign_keys=ON`, `busy_timeout=5000`. One file, default
`/var/lib/vrioscu/vrioscu.db` in production, created `0600` in a `0700` directory.
It is never inside `app/static/`, never served by nginx (explicit deny rules), and never reachable over HTTP.

## Migrations

`migrations/NNNN_description.sql`, applied in filename order by `app/db.py:migrate()`.
Applied versions are tracked in `schema_migrations`. Each file runs inside one
transaction, so a failing migration leaves the database unchanged.

- Runs automatically at app start and via `flask --app wsgi init-db` (also `ExecStartPre` in systemd).
- Never edit an applied migration. Add `0002_….sql`.
- Back up before deploying a release that adds migrations.

## Tables (migration 0001)

| Table | Purpose | Personal data | Deleted when |
|---|---|---|---|
| `users` | Accounts and profile | username, email, optional names/country/purpose | User deletes account |
| `sessions` | Server-side sessions; SHA-256 of cookie token, CSRF secret, timestamps | none beyond user link | Logout/expiry (purged by maintenance), account deletion (cascade) |
| `product_update_preferences` | Current opt-in (default off) | link to user | Account deletion (cascade) |
| `consent_records` | Append-only history: privacy-notice acknowledgement, opt-in changes, notice version | link to user | Account deletion (cascade) |
| `feedback` | Product feedback | message text | Account deletion (cascade) |
| `support_requests` | Contact form | name, email, message | Cascade if sent while signed in; otherwise per retention policy |
| `releases` | Release metadata | none | Admin deletes |
| `download_stats` | Count per release per day | **none** (no IP, no user) | Release deleted (cascade) |
| `rate_limits` | Fixed-window counters keyed by HMAC digests | **none** (no raw IP/email) | Purged after 24 h |
| `audit_log` | Admin actions (who, what, target) | admin user link | Retained; actor set NULL if that admin is deleted |

Constraints enforced in the schema: role ∈ {user, admin}; channel ∈ {PUBLIC_BETA, STABLE, INTERNAL, DEV};
feedback/support status enums; `sha256` length 64; `file_size_bytes > 0`; unique `(version, channel)`;
case-insensitive unique username and email.

## Not stored, by design

Plaintext passwords, raw session tokens, IP addresses, user agents, analytics,
anything from the desktop application's validation runs.

## Timestamps

ISO-8601 UTC strings, `YYYY-MM-DDTHH:MM:SSZ`.
