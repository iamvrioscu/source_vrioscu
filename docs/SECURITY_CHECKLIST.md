# Security checklist

Status key: **✔ implemented and tested** · **◐ implemented, needs operator action** · **✘ not implemented (see notes)**

## Transport and headers

| Control | Status | Where |
|---|---|---|
| HTTPS-only production | ✔ | Startup refuses non-HTTPS `BASE_URL`; nginx redirects 80→443 |
| HSTS (2 years, subdomains) | ✔ | `security.apply_security_headers` when HTTPS; nginx for static |
| Content-Security-Policy, no `unsafe-inline`/`unsafe-eval` | ✔ | `default-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `form-action 'self'`, `base-uri 'self'`; test asserts no inline script/style |
| X-Content-Type-Options `nosniff` | ✔ | App and nginx |
| Referrer-Policy `strict-origin-when-cross-origin` | ✔ | App |
| Frame protection | ✔ | `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` |
| Permissions-Policy | ✔ | Camera, microphone, geolocation, payment, USB disabled |
| COOP / CORP | ✔ | `same-origin` |
| `Cache-Control: no-store` on private pages | ✔ | Account, admin, `/api/v1/me*`, `/api/v1/admin*`, exports |
| Server banner hidden | ◐ | `server_tokens off` in nginx config |
| TLS 1.2+ only, OCSP stapling | ◐ | nginx config; run an external TLS scan after go-live |

## Authentication and sessions

| Control | Status | Where |
|---|---|---|
| Salted, slow password hashing | ✔ | scrypt N=32768 r=8 p=1 |
| No plaintext passwords stored, logged or echoed | ✔ | Password fields never re-rendered; log redaction filter; tests |
| Password hashes never exposed | ✔ | Output allowlist (`public_user`), export forbidden columns; tests |
| Password policy | ✔ | 12–128 chars, common-password list, can't contain username/email name |
| Generic login errors, timing equalised | ✔ | Same message; dummy hash check for unknown accounts |
| Authentication throttling | ✔ | Per-IP and per-identifier limits; lockout after 5 failures for 15 min |
| Server-side sessions, hashed tokens | ✔ | `sessions` table stores SHA-256 only |
| Secure cookies | ✔ | `HttpOnly`, `SameSite=Lax`, `Secure` + `__Host-` prefix on HTTPS |
| Idle and absolute expiration | ✔ | 60 min / 12 h (configurable) |
| Session rotation on login | ✔ | Old session revoked |
| Invalidation on logout, password change, account disable | ✔ | Tests cover each |
| Logout is POST + CSRF | ✔ | GET returns 405 |
| Password reset by email | ✘ | Needs an email provider. Users contact support. See PRODUCTION_READINESS |
| Multi-factor authentication for admins | ✘ | Recommended before scaling the admin team |

## Authorisation

| Control | Status | Where |
|---|---|---|
| Server-side checks on every private route | ✔ | `@login_required`, `@admin_required`; tests hit every admin page/API as user and anonymous |
| No reliance on hidden UI | ✔ | Test: user who knows admin URLs gets 403 |
| No web path to become admin | ✔ | Role not accepted from forms/API; admin only via CLI |
| Users can't access others' data | ✔ | Personal export and `/me` are scoped to session user; tests |
| Admin can't disable self; last admin can't self-delete | ✔ | Tests |
| Admin actions audited | ✔ | `audit_log` for user status, inbox status, releases, exports |

## Input, output and data handling

| Control | Status | Where |
|---|---|---|
| Input validation on every write | ✔ | `validation.py` field specs; unknown fields ignored; control characters stripped |
| Output encoding | ✔ | Jinja2 autoescaping; JSON via Flask |
| SQL injection | ✔ | Parameterised queries only; dynamic identifiers from fixed allowlists; `LIKE` escaping; test with payloads |
| CSRF | ✔ | Synchronizer tokens on all unsafe methods + Origin check |
| CORS | ✔ | Same-origin; allowlisted origins only for public read-only release GETs |
| Request size limit | ✔ | 64 KB (app) and nginx `client_max_body_size 64k` |
| Open redirect | ✔ | `safe_next` accepts only same-site relative paths; tests |
| Spreadsheet formula injection | ✔ | `safe_cell`; test |
| No arbitrary command execution | ✔ | No `subprocess`, `os.system`, `eval`, `exec` anywhere in `app/` |
| No unsafe deserialisation | ✔ | No `pickle`/`yaml.load`; JSON only |
| No user-controlled file paths | ✔ | No file uploads; static served by Flask/nginx with traversal protection; test |
| Safe download handling | ✔ | HTTPS-only, no private hosts, optional host allowlist, re-validated on redirect; the site never serves or runs executables |
| Spam protection on contact form | ✔ | Honeypot + rate limit |

## Secrets and configuration

| Control | Status | Where |
|---|---|---|
| Secrets from environment only | ✔ | `config.py`; `.env.example` holds placeholders only |
| `.env`, databases, backups git-ignored | ✔ | `.gitignore` |
| No secrets or cloud credentials in frontend | ✔ | No API keys exist; JS has no configuration |
| Startup refuses weak production config | ✔ | Tests |
| Debug mode never on | ✔ | `DEBUG=False` forced; test |
| Env file permissions | ◐ | `/etc/vrioscu/vrioscu.env` root:vrioscu 0640 |

## Errors and logging

| Control | Status | Where |
|---|---|---|
| No stack traces, paths, DB details in responses | ✔ | Central handlers; test raises an exception containing a path |
| Branded error pages | ✔ | 403, 404, 429, 500, generic |
| Structured JSON logs with request IDs | ✔ | `logging_setup.py` |
| Secrets redacted from logs | ✔ | Key-based redaction (password, token, secret, csrf, cookie, hash, session…) |
| Security events logged | ✔ | Login success/failure/lockout, CSRF failure, rate limit, authz denial, admin actions, exports |

## Storage

| Control | Status | Where |
|---|---|---|
| Database outside public directories | ✔ | Startup check + nginx deny rules |
| Database file `0600`, directory `0700` | ✔ | `db.py` and systemd `UMask=0077`; test |
| SQLite never exposed over HTTP | ✔ | No route serves it; tests |
| Backups integrity-checked, `0600` | ✔ | `backup_db.py`; tests |
| Off-host backups | ◐ | EBS snapshots or S3 (BACKUP_RESTORE.md) |
| Data minimisation | ✔ | No IPs, user agents or analytics stored; download counts anonymous |

## Host and supply chain

| Control | Status | Notes |
|---|---|---|
| Least-privilege service account, systemd sandbox | ◐ | `deploy/systemd/vrioscu.service` |
| App bound to loopback only | ◐ | gunicorn `127.0.0.1:8000`; don't open 8000 in the security group |
| Minimal dependencies, pinned | ✔ | Flask, Werkzeug, openpyxl, gunicorn |
| Dependency vulnerability scanning | ◐ | Run `pip install pip-audit && pip-audit -r requirements.txt` in CI and monthly |
| OS patching | ◐ | `unattended-upgrades` |

## Desktop-related commitments

The website never tells users to disable SmartScreen, Smart App Control or
Defender, never suggests firewall/antivirus exclusions, never installs services
or persistence, never claims the installer is signed/verified/certified unless
configured as such, and never claims to collect machine/network data from a browser.
`tests/test_config_and_security.py::BrandingTests` checks key pages for forbidden claims.
