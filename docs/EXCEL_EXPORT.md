# Excel export

## Administrator exports

**Admin → Exports**, or `POST /api/v1/admin/exports/{dataset}`. Admin role required;
CSRF-protected `POST` (so a link or image can't trigger one); 30 exports/hour per admin;
every export recorded in `audit_log` with the dataset and row count.

| Dataset | Columns |
|---|---|
| `users` | ID, Username, Email, First name, Last name, Country, Main use, Role, Status, Product updates, Created (UTC), Last sign-in (UTC) |
| `subscribers` | ID, Username, Email, First name, Last name, Opted in (UTC). Active accounts with product updates on only |
| `feedback` | ID, Submitted (UTC), Username, Category, App version, Status, Message |
| `support` | ID, Submitted (UTC), Name, Email, Topic, Status, Message |
| `releases` | ID, Version, Channel, Release date, Published, Mandatory, Signed, Minimum supported, Installer, Size (bytes), SHA-256, Download URL, Release notes URL, Downloads |

There is no separate "Public Beta registrations" table: every account is a
Public Beta participant during the beta, so use `users` (with Main use) or `subscribers`.

## Personal export (any signed-in user)

**Account → Your data → Download my data**. Contains only the signed-in user's
profile, product-update choice, consent history, feedback and support messages.
There is no parameter that selects another user.

## Safeguards

- **Column allowlists.** Each dataset declares exactly which columns it outputs.
- **Forbidden-column guard.** `password_hash`, `password`, `token_hash`, `csrf_secret`, `secret`, `api_key`,
  `private_key`, `session_token`, `failed_login_count`, `locked_until` can never appear; an assertion runs at import.
- **Formula-injection protection (CWE-1236).** Text cells starting with `=`, `+`, `-`, `@`, tab, CR or LF are
  prefixed with `'` so Excel shows them as text instead of executing them.
- **No caching.** `Cache-Control: no-store`, `Content-Disposition: attachment`.
- Up to 100,000 rows per sheet.

## Format

`.xlsx` via openpyxl: dark header row, frozen header, auto-filter, sized columns, UTC timestamps.
File name `vrioscu-<dataset>-YYYY-MM-DD.xlsx`.

## Handling exported files

Exports contain personal data. Keep them on managed storage, don't email them
around, and delete them when the task is done. Only email product updates to
people in the `subscribers` export.
