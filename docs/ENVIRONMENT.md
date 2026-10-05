# Environment variables

Loaded from the process environment; in development also from `.env` (existing
variables win). In production put them in `/etc/vrioscu/vrioscu.env`
(owner `root:vrioscu`, mode `0640`). Template: `.env.example`. **Never commit `.env`.**

## Application

| Variable | Required | Default | Description |
|---|---|---|---|
| `APP_ENV` | yes (prod) | `development` | `development`, `test` or `production`. Production enables strict startup checks |
| `SECRET_KEY` | **prod** | random per process in dev | ≥32 random chars. Signs CSRF tokens, keys rate-limit digests. Rotating it invalidates CSRF tokens (users re-load forms) but not sessions |
| `BASE_URL` | yes | `http://127.0.0.1:5000` | Public origin. Must be `https://` in production. Used for canonical URLs, sitemap, origin check |
| `DATABASE_PATH` | yes | `instance/vrioscu.db` | SQLite file. Relative paths resolve from the repo root. Refused inside `app/static` in production |
| `TRUSTED_PROXY_COUNT` | prod | `0` | Proxies in front of the app. Set `1` behind nginx. Leave `0` if exposed directly (don't do that) |
| `SESSION_IDLE_MINUTES` | no | `60` | Inactivity timeout |
| `SESSION_ABSOLUTE_HOURS` | no | `12` | Maximum session lifetime |
| `LOGIN_MAX_FAILURES` | no | `5` | Failed sign-ins before lockout |
| `LOGIN_LOCK_MINUTES` | no | `15` | Lockout duration |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `CORS_PUBLIC_ORIGINS` | no | empty | Comma-separated origins allowed to `GET /api/v1/releases*` |
| `DOWNLOAD_ALLOWED_HOSTS` | recommended | empty | Comma-separated hosts allowed in release download URLs (e.g. `downloads.vrioscu.com`) |

## Product (central configuration)

| Variable | Default | Description |
|---|---|---|
| `PRODUCT_NAME` | `VRIOSCU` | Brand name everywhere |
| `PRODUCT_VERSION` | `1.0.0` | Shown site-wide |
| `RELEASE_CHANNEL` | `PUBLIC_BETA` | Channel the download page shows |
| `PUBLIC_BETA` | `true` | Shows Public Beta labelling and notices |
| `WINDOWS_COMPATIBILITY` | `Windows 10 and Windows 11 (64-bit)` | **Confirm against tested platforms before launch** |
| `INSTALLER_SIGNED` | `false` | `true` only when the installer is actually Authenticode-signed |
| `DOWNLOAD_URL` | empty | Fallback HTTPS installer URL when no release is published in the database |
| `RELEASE_NOTES_URL` | empty | Fallback release notes |
| `INSTALLER_FILENAME` | empty | Fallback file name |
| `INSTALLER_SHA256` | empty | Fallback checksum, 64 hex |
| `INSTALLER_SIZE_BYTES` | empty | Fallback size |
| `SUPPORT_EMAIL` | empty | Shown on contact page if set; otherwise the form is the contact route |
| `PRIVACY_EMAIL` | empty | Shown on privacy/contact pages if set |
| `GENERAL_EMAIL` | empty | Shown on contact page if set |
| `PRIVACY_NOTICE_VERSION` | `2026-10-01` | Recorded with each account's privacy acknowledgement. Change it when the notice changes |

Prefer publishing releases through **Admin → Releases**; the `DOWNLOAD_*`/`INSTALLER_*`
variables are a fallback only.
