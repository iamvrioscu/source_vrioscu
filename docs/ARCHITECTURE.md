# Architecture

## 1. Responsibility boundary

| Windows desktop application | Website (this repository) |
|---|---|
| Validate endpoints | Product presentation and documentation |
| Capture visual evidence | Public Beta information |
| Collect hostname, local IP, gateway, DNS, SSID, signal, frequency/channel, NIC/radio | Download and release metadata |
| Analyze evidence, optional AI Validation Insights | Accounts, profiles, product-update preference |
| Generate PDF reports | Feedback, support, administration, exports |

The website has **no endpoint that accepts validation data**, and no page attempts
to read local machine or network information (browsers block this by design).
The only website → desktop interaction is the installer download and the public,
read-only release API that a desktop update check can call.

## 2. Deployment topology

```
Internet ──HTTPS──▶ nginx (EC2, :443)
                     ├─ /static/*  served from disk
                     └─ everything else ──▶ gunicorn 127.0.0.1:8000 (3 workers)
                                                 └─ Flask app ──▶ SQLite /var/lib/vrioscu/vrioscu.db
```

No RDS, Lambda, API Gateway, ECS or Kubernetes. One instance, one process
group, one database file. See `DEPLOYMENT.md`.

## 3. Request lifecycle

1. `ProxyFix` (only when `TRUSTED_PROXY_COUNT>0`) restores client IP and scheme from nginx.
2. `before_request`: assign request ID → open SQLite connection → resolve session cookie
   (hash lookup, idle/absolute expiry, account active) → **CSRF check** on every unsafe method.
3. Route handler: rate limit (if applicable) → validate input → call repositories inside a `transaction()`.
4. `after_request`: set/clear cookies → security headers → structured request log line.
5. `teardown_request`: roll back any open transaction, close connection.
6. Errors: one handler renders branded HTML pages or JSON `{error:{code,message,request_id}}`.
   Stack traces are never sent to clients.

## 4. Layers

| Layer | Location | Rule |
|---|---|---|
| Routes | `app/routes/` | HTTP only: parse, authorise, call services/repositories, render |
| Validation | `app/validation.py`, `app/forms.py` | Every write passes a field allowlist; unknown fields are ignored |
| Services | `app/services/` | Business rules (auth, sessions, releases, exports) |
| Repositories | `app/repositories/` | **The only place SQL exists.** Parameterised queries; dynamic column names only from fixed allowlists |
| DB | `app/db.py` | Connections, `transaction()` (nested → savepoints), migrations |

HTML forms and the JSON API share the same field sets, services and authorisation
decorators, so behaviour can't drift between them.

## 5. Authentication and sessions

- Passwords: Werkzeug scrypt (`N=32768, r=8, p=1`), salted. A dummy hash check runs for unknown
  accounts to equalise timing. Minimum 12 characters, common-password and username checks.
- Sessions are server-side rows. The cookie holds 32 random bytes; the DB stores its SHA-256.
  Cookie: `HttpOnly`, `SameSite=Lax`, and in production `Secure` with the `__Host-` prefix.
- Expiry: idle (`SESSION_IDLE_MINUTES`) and absolute (`SESSION_ABSOLUTE_HOURS`).
- Rotation: a new session on every login; password change revokes all other sessions;
  disabling an account revokes all its sessions.
- Throttling: per-IP and per-identifier limits plus account lockout after `LOGIN_MAX_FAILURES`.

## 6. Authorisation

Two roles: `user`, `admin`. `@login_required` and `@admin_required` guard every
private route on the server. Hidden buttons are never the control. Admins are
created only through the `flask create-admin` CLI; there is no web path to gain admin.

## 7. CSRF

Synchronizer tokens = HMAC(SECRET_KEY, session CSRF secret), or for anonymous
visitors HMAC over a random `vr_csrf` cookie. Forms send `csrf_token`; the API
sends `X-CSRF-Token`. A mismatched `Origin` header is rejected as a second check.

## 8. Rate limiting

Fixed-window counters in the `rate_limits` table (so limits hold across gunicorn
workers). Keys are HMAC digests: no raw IP or email is stored. nginx adds a
coarser limit at the edge.

| Limiter | Limit |
|---|---|
| Login per IP | 20 / 10 min |
| Login per identifier | 10 / 10 min |
| Registration per IP | 5 / hour |
| Contact/support per IP | 5 / hour |
| Feedback per user | 10 / hour |
| Password change / account delete per user | 5 / 15 min |
| Admin exports per admin | 30 / hour |
| Public release API per IP | 120 / min |
| Download redirects per IP | 30 / 5 min |

## 9. Central configuration

`app/config.py` is the single source for product name, website URL, version,
channel, Public Beta status, Windows compatibility, signing status, fallback
download URL / release notes / checksum, and contact addresses. Templates read
it through the `product` variable. Production refuses to start if `SECRET_KEY`
is weak, `BASE_URL` isn't HTTPS, `DOWNLOAD_URL` isn't HTTPS, or the database
path is inside a public directory.

## 10. Replacing SQLite with PostgreSQL

Frontend, routes and services don't change. Work required:

1. Translate `migrations/0001_initial.sql` (`INTEGER PRIMARY KEY` → `BIGSERIAL`, `COLLATE NOCASE` → `CITEXT` or
   lower-cased unique indexes, `CHECK` constraints carry over unchanged).
2. Re-implement `app/db.py` (`connect`, `transaction`, `migrate`) with psycopg.
3. In repositories: `?` placeholders → `%s`; keep the `ON CONFLICT … DO UPDATE` upserts (PostgreSQL supports
   the same syntax); `RETURNING` already used.
4. Copy data with a one-off script reading through the SQLite repositories and writing through the new ones.

The repository interface (methods returning plain dicts) is the contract.

## 11. Front end

Server-rendered, semantic HTML; one CSS file, one small progressive-enhancement
script (mobile menu, copy-to-clipboard, confirm dialogs). No inline scripts or
styles, so the CSP needs no `unsafe-inline`. Diagrams are inline SVG styled from
CSS. Fonts are self-hosted (no third-party requests).
