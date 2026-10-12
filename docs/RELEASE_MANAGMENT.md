# Release management

Admin → Releases accepts direct Windows `.exe` uploads to private EC2 storage.
See [INSTALLER_STORAGE.md](INSTALLER_STORAGE.md) for setup, ownership, limits,
endpoint contracts, deployment, backups and verification status.

Enter version/channel/date/minimum version/optional HTTPS notes, select the file,
upload and wait for saved-file verification. Filename and byte size are populated
automatically; SHA-256 stays internal to integrity verification and the existing
desktop update API. Save a draft, review it, then explicitly tick Published and
save. The server re-verifies file bytes before publication. Signed status remains
an administrator assertion about a valid Authenticode signature; the website
does not build, sign, run or install executables.

The existing `(version, channel)` uniqueness and semantic version checks remain.
Public Beta and Stable become visible only when published and their installer is
available. Internal and Dev remain private. With no eligible release the public
site displays Coming Soon; environment metadata never creates a fallback release.

`BASE_URL` plus `/download/<release-id>` creates the stable public URL. Production
requires HTTPS. Nginx serves the file through an internal location after the app's
publication gate when enabled; Werkzeug streams it with Range support otherwise.
The original filename is an attachment header, never a filesystem path. Daily
download counts and admin audit history remain in the existing database.

Unpublish or delete to block subsequent public requests immediately. Previously
attached files are retained for backup/recovery; new uploads never replace them.
Existing externally hosted releases and their validated HTTPS/API integrations
remain compatible. The HTML form uses direct upload for every new release.

Desktop update check remains:

```text
GET /api/v1/releases/latest?channel=PUBLIC_BETA&current_version=1.0.0
```

It returns version, size, signing status, update flags, integrity metadata and the
tracked download path. Clients should independently verify downloaded bytes and
present updates for user review. No client is instructed to execute a download.
