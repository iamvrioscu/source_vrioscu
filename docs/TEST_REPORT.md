# Test report

**Result: 99 tests, 99 passed, 0 failed, 0 skipped.** Run time about 20 seconds.

| | |
|---|---|
| Date | 2026-10-05 |
| Python | 3.12.3 |
| Flask | 3.1.3 |
| openpyxl | 3.1.5 |
| SQLite | 3.45.1 |
| Command | `python -m unittest discover -s tests -t . -v` |

Each test runs against a fresh temporary SQLite database through Flask's test client, exercising the real request lifecycle (CSRF, sessions, rate limits, headers, error handlers). Security components are not mocked.

## Coverage against the requirements

| Requirement | Covered by |
|---|---|
| Registration | `RegistrationTests` |
| Login / logout | `LoginTests`, `SessionTests` |
| Profile | `ProfileTests` |
| Authentication (hashing, sessions, expiry, rotation) | `RegistrationTests`, `SessionTests`, `PasswordAndDeletionTests` |
| Authorisation and admin authorisation | `AuthorizationTests` |
| Input validation | `RegistrationTests.test_invalid_inputs`, `ReleaseManagementTests.test_field_validation`, `FeedbackAndSupportTests` |
| Rate limiting | `RateLimitTests`, lockout in `LoginTests` |
| Excel export authorisation and content | `ExportTests`, `SelfExportTests`, `AuthorizationTests` |
| Release management and download metadata | `ReleaseManagementTests` |
| Database operations, backup and restore | `DatabaseTests`, `BackupRestoreTests` |
| Security headers | `HeaderTests`, `HttpsHeaderTests` |
| Production configuration | `ProductionConfigTests` |
| Unauthorised users can't access admin APIs, export others' data, modify releases, access private records or files | `AuthorizationTests`, `SelfExportTests`, `FileExposureTests` |
| Honest product claims and branding | `BrandingTests` |
| SEO basics | `SeoTests` |
| Error handling hides internals | `ErrorHandlingTests` |
| Pages render, no inline script/style | `PublicPagesTests` |

## Tests by file

| File | Classes (tests) |
|---|---|
| `test_config_and_security.py` | ProductionConfigTests (6), HeaderTests (2), HttpsHeaderTests (1), CsrfTests (4), FileExposureTests (2), ErrorHandlingTests (4), SeoTests (3), BrandingTests (2) |
| `test_auth.py` | RegistrationTests (7), LoginTests (6), SessionTests (6) |
| `test_account.py` | ProfileTests (6), PasswordAndDeletionTests (3), FeedbackAndSupportTests (5), SelfExportTests (2) |
| `test_admin_and_authz.py` | AuthorizationTests (8), ExportTests (4) |
| `test_releases.py` | ReleaseManagementTests (13) |
| `test_rate_limit_and_db.py` | RateLimitTests (3), DatabaseTests (6), PublicPagesTests (3) |
| `test_backup.py` | BackupRestoreTests (3) |

Run with `-v` to see every individual test name and result.

## Manual verification performed

- Rendered public pages in headless Chromium at 1280–1440 px and 390 px (mobile) and reviewed the screenshots
  for layout, overflow and the download page's empty and populated states.
- Code audit: no `subprocess`, `os.system`, `eval`, `exec`, `pickle` or `send_file` in `app/`; the only formatted
  SQL interpolates column names from fixed allowlists; no hard-coded secrets; no forbidden brand names.

## Not covered by automated tests

- nginx and systemd configuration. Verify on the server with `nginx -t`, `systemd-analyze security vrioscu`
  and the curl checks in DEPLOYMENT.md.
- Real TLS behaviour and certificate renewal.
- Screen-reader walkthrough. Structure, labels, focus states and skip link are in place; a manual pass with
  NVDA or Narrator is recommended before launch.
