# API reference (v1)

Base path: `/api/v1`. JSON in and out. All production traffic is HTTPS.

## Conventions

**Authentication.** The website session cookie (set by signing in at `/login`).
There are no API keys and no bearer tokens.

**CSRF.** Every `POST`, `PUT`, `PATCH` and `DELETE` must send `X-CSRF-Token`.
Get it from `GET /api/v1/me` (`csrf_token`) or from the page's
`<meta name="csrf-token">`. Missing or wrong token → `400`.

**Bodies.** `Content-Type: application/json`, top-level object, maximum 64 KB.
Wrong type → `415`; non-object → `400`; too large → `413`.

**CORS.** Same-origin only, except `GET /api/v1/releases*`, which returns
`Access-Control-Allow-Origin` for origins listed in `CORS_PUBLIC_ORIGINS`.

**Errors.** Always:

```json
{ "error": { "code": "validation_failed", "message": "Some fields need attention.",
             "fields": { "email": "Enter a valid email address, like name@example.com." },
             "request_id": "4f1c2a9e7b3d5a10" } }
```

| Status | `code` | When |
|---|---|---|
| 400 | `bad_request` | Malformed input, CSRF failure |
| 401 | `unauthenticated` | Not signed in |
| 403 | `forbidden` | Signed in without permission, or cross-site request |
| 404 | `not_found` | Unknown resource, unpublished or non-public release |
| 413 | `payload_too_large` | Body > 64 KB |
| 415 | `unsupported_media_type` | Body not JSON |
| 422 | `validation_failed` | Field errors in `fields` |
| 429 | `rate_limited` | See `Retry-After` header |
| 500 | `server_error` | Logged with `request_id`; no internals returned |

Every response has an `X-Request-ID` header.

---

## Public

### `GET /health`
`200 {"status":"ok"}` or `503 {"status":"degraded"}` if the database can't be read.

### `GET /releases/latest`
Latest **published** release in a public channel. Intended for the desktop update check.

| Query | Default | Notes |
|---|---|---|
| `channel` | `PUBLIC_BETA` | `PUBLIC_BETA` or `STABLE`. `INTERNAL`/`DEV` → 404 |
| `current_version` | — | Optional `MAJOR.MINOR.PATCH`; adds update flags |

```json
{ "release": {
    "version": "1.1.0", "channel": "PUBLIC_BETA", "release_date": "2026-11-01",
    "release_notes_url": "https://…", "installer_filename": "VRIOSCU-Setup-1.1.0.exe",
    "sha256": "…64 hex…", "file_size_bytes": 52428800, "is_mandatory": false,
    "minimum_supported_version": "1.0.5", "is_signed": false,
    "download_path": "/download/2",
    "update_available": true, "update_required": true } }
```

`update_required` is true when the release is mandatory **or** `current_version`
is below `minimum_supported_version`. `download_path` goes through the counted,
validated redirect; the raw storage URL isn't exposed. The website never runs
or serves executables itself; the desktop app decides what to do with this data.

### `GET /releases`
`{"releases":[…]}`: all published Public Beta and Stable releases, newest first.

### `POST /support`
Anonymous or signed-in. Rate limited (5/hour/IP).

```json
{ "name": "Sam", "email": "sam@example.com", "topic": "installation",
  "message": "The installer was blocked on my work laptop." }
```
`topic`: `installation`, `account`, `reports`, `privacy`, `general`. Message 10–4000 chars.
→ `201 {"support_request":{"id":12,"status":"new"}}`

---

## Signed-in user

### `GET /me`
```json
{ "user": { "id": 3, "username": "alice", "email": "alice@example.com", "first_name": "Alice",
            "last_name": "", "country": "India", "purpose": "site_integration", "role": "user",
            "created_at": "2026-10-05T09:00:00Z", "last_login_at": "2026-10-05T09:00:00Z" },
  "product_updates": false, "csrf_token": "…" }
```
Only these fields are ever serialised. Password hashes, session data and lockout counters never appear.

### `PATCH /me`
Partial update of `email`, `first_name`, `last_name`, `country`, `purpose`. Other keys (e.g. `role`) are ignored.
`country` must be a name from the site's country list; `purpose` one of
`network_validation`, `site_integration`, `change_verification`, `it_support`, `qa_testing`, `evaluation`, `other`.

### `PUT /me/preferences`
`{"product_updates": true}` (boolean required). Each change is recorded in consent history.

### `POST /feedback`
```json
{ "category": "report", "app_version": "1.0.0", "message": "The summary table could be wider." }
```
`category`: `bug`, `usability`, `report`, `feature`, `other`. `app_version` optional semver. 10/hour/user.
→ `201 {"feedback":{"id":5,"status":"new"}}`

---

## Administrator (`role = admin`; others get 403, anonymous 401)

| Method & path | Description |
|---|---|
| `GET /admin/users?q=&limit=50&offset=0` | Users (no secrets). `q` searches username, email, names. `limit` ≤ 200 |
| `GET /admin/feedback?status=&limit=&offset=` | Feedback. `status`: `new`, `reviewed`, `closed` |
| `GET /admin/support?status=&limit=&offset=` | Support requests. `status`: `new`, `in_progress`, `closed` |
| `GET /admin/releases` | All releases, all channels, drafts included |
| `POST /admin/releases` | Create (body below) → `201` |
| `PATCH /admin/releases/{id}` | Partial update; merged with the stored record and fully re-validated |
| `DELETE /admin/releases/{id}` | → `204` |
| `POST /admin/exports/{dataset}` | `.xlsx` download. Datasets: `users`, `subscribers`, `feedback`, `support`, `releases` |

Release body:

```json
{ "version": "1.0.1", "channel": "PUBLIC_BETA", "release_date": "2026-10-20",
  "download_url": "https://downloads.vrioscu.com/VRIOSCU-Setup-1.0.1.exe",
  "release_notes_url": "https://vrioscu.com/…", "installer_filename": "VRIOSCU-Setup-1.0.1.exe",
  "sha256": "…64 lowercase hex…", "file_size_bytes": 52428800,
  "minimum_supported_version": "", "is_mandatory": false, "is_signed": false, "is_published": true }
```

Validation highlights: `download_url` must be public HTTPS (no localhost, private IPs,
credentials in the URL, `file://` or UNC paths) and, if `DOWNLOAD_ALLOWED_HOSTS` is set, on an allowed host;
`installer_filename` is a bare name ending `.exe`, `.msi`, `.msix` or `.zip`; `(version, channel)` is unique;
`minimum_supported_version` can't exceed `version`. Every create/update/delete/export is written to `audit_log`.

## HTML endpoints (non-API)

`/download/latest` and `/download/{id}`: 302 to the installer URL after re-validating it, incrementing an
anonymous daily counter. `/robots.txt`, `/sitemap.xml`: generated from `BASE_URL`.
