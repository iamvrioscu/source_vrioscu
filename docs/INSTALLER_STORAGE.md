# Direct Windows installer uploads

## Implementation and verification status

The existing Flask/Jinja release catalog, SQLite database, admin sessions,
CSRF protection, channels, update API and public `/download/<id>` routes are
preserved. Installers now upload through the existing admin release form.
No additional hosting, DNS provider or object storage is involved.

Repository deployment files target Ubuntu, Nginx and Gunicorn. **The live EC2 OS,
filesystem/mount, free bytes, service identity and installed Nginx configuration
have not been inspected: no EC2 connection identifier was available.** The paths
below are a proposed Ubuntu setup, not a claim about the current instance. Verify
the server before choosing the path or installing these files.

On 2026-10-12 a direct, certificate-verified connection to `vrioscu.com` negotiated
TLS 1.3; its certificate expires 2027-01-06 12:45:04 UTC. HTTPS HEAD `/` and
`/download` returned 200; `/download/latest` returned 404. This verifies the
existing site's TLS only. **The new upload and installer download have not been
deployed or tested on that domain.** Keep the existing Wix DNS and Elastic IP.

## Administrator workflow

1. Open Admin → Releases → Add release. Enter version, channel, release date,
   optional minimum version and HTTPS release notes. Select an `.exe`.
2. The form displays the original filename and exact byte size. Click Upload.
   The browser transfers at most 8 MiB per request and shows progress. After an
   interruption, click Retry; after a refresh reselect the same unchanged file
   and click Resume. Resume IDs stay in that tab's session storage for 24 hours.
3. Completion reads the saved file with a 1 MiB buffer, checks its Windows PE
   signature and machine header, verifies actual size, and computes SHA-256.
   Only after fsync and atomic placement does the UI report verified success.
   The server never executes or installs the file. Header checks do not establish
   publisher identity or validate Authenticode: the Signed checkbox remains the
   administrator's assertion about the build's independently verified signature.
4. Save draft and review. Upload metadata fills filename, bytes, upload time and
   internal checksum automatically. New uploads cannot be published in the same
   operation that attaches them to a release. Review the saved draft, tick
   Published, and save. Publication re-hashes the stored file and checks size.
5. For Public Beta/Stable, the generated URL is
   `BASE_URL + /download/<release-id>`. Production requires an HTTPS `BASE_URL`.
   Public links use that same route; no manually entered URL or public checksum
   field is added. The existing desktop API retains integrity metadata.
6. Unpublishing or deleting the release immediately blocks subsequent downloads.
   A transfer already authorized and in progress can finish. Deleted metadata
   does not delete its immutable binary: retain it for recovery and review disk
   retention manually. Uploading a later version never overwrites an earlier file.

Existing externally hosted releases remain compatible, including their API
integration and validated HTTPS redirects. Their form retains existing asset
metadata until a direct upload replaces it. All newly created HTML releases
require a verified direct upload. Internal and Dev channels stay private.

## Routes and implementation files

| Route | Purpose |
|---|---|
| `POST /api/v1/admin/release-uploads` | Reserve capacity; create owned transfer from filename and size |
| `GET /api/v1/admin/release-uploads/<32-hex-id>` | Return durable committed offset and state |
| `PUT /api/v1/admin/release-uploads/<id>` | Raw octet-stream chunk with `Upload-Offset` and Content-Length |
| `POST /api/v1/admin/release-uploads/<id>/complete` | Verify and durably place immutable file |
| `DELETE /api/v1/admin/release-uploads/<id>` | Cancel and remove unattached transfer bytes |
| `/admin/releases/new`, `/admin/releases/<id>` | Existing draft, edit and publication form |
| `GET/HEAD /download/<id>`, `/download/latest` | Existing publication gate; local streaming or legacy redirect |

Backend: `app/services/installers.py`, `app/routes/uploads.py`, existing
`app/routes/admin.py`, `app/routes/public.py`, `app/routes/api.py`,
`app/services/releases.py`, `app/config.py`, `app/__init__.py` and repositories.
UI: `app/templates/admin/release_form.html`, `app/static/js/release-upload.js`,
`app/static/css/site.css`. Migration: `0006_installer_storage.sql` adds nullable
storage key/upload timestamp to releases and temporary transfer state. No
existing release, download count or account is removed. Existing nullable
checksum migration 0005 remains in order. Back up before migrating.

## Storage layout, limits and failure recovery

`RELEASE_STORAGE_PATH` must be absolute, private, outside the checkout, and in
production outside temporary storage. Production requires this explicit setting;
the service does not provision directories automatically. Development defaults
to `%LOCALAPPDATA%/VRIOSCU/WebsiteReleases` on Windows, or
`~/.local/share/VRIOSCU/WebsiteReleases` elsewhere. Tests use isolated directories.
There is no confirmed live installer path yet.

Within the selected root:

* `staging/<random-id>.part`: private incomplete bytes, never downloadable.
* `objects/<random-id>.exe`: immutable completed file; only published DB rows
  authorize a download. Original filenames never become filesystem paths.
* `locks/<random-id>.lock`: tiny cross-process OS locks, deliberately retained;
  removing active lock files would break mutual exclusion.

The staging and objects directories must share a filesystem. Completion uses an
atomic hard link that fails rather than replacing an existing filename, syncs
the directory, and removes the stage. A crash between placement and DB commit
is recovered by retrying completion. Chunk bytes are synced before SQLite records
their offset; uncommitted tails from interrupted requests are truncated on retry.
Retries of committed offsets must match the saved bytes exactly.

Defaults: maximum installer 2 GiB (`RELEASE_MAX_BYTES`, configurable up to 8 GiB),
minimum free reserve 1 GiB (`RELEASE_MIN_FREE_BYTES`), 8 MiB chunk, three active
uploads per admin, 24-hour transfer lifetime. Start checks actual filesystem free
bytes minus outstanding upload reservations; each chunk checks free space again.
HTTP 507 reports insufficient space. Do not reduce the reserve without budgeting
SQLite, logs, Nginx buffers, backups and other applications on that volume.

All transfer endpoints require active admin authorization. Mutations additionally
require same-origin CSRF. Upload IDs are owner-scoped. File extension, filename,
size, offset, PE header and checksum are validated server-side. Symlinks and unsafe
storage keys are rejected. Request memory is bounded by the streaming buffer;
installer size does not determine Python memory use. Full-file hashing happens
outside the release-save database write transaction.

The existing scheduled `scripts/maintenance.py` cancels expired unattached
transfers and removes only their generated staging/object paths. It never removes
an attached installer, including one whose release was later deleted. Start also
performs expired-transfer cleanup. Failed verification leaves a private transfer
that can be cancelled immediately or cleaned after expiry. No filesystem glob
deletion is used. Keep the database together with the files so ownership can be
resolved safely. Cancelled upload rows and small lock files are retained for
audit/retry safety; their growth is bounded operationally by the start rate limit.

## Verify EC2 before provisioning (operator action)

Connect using the existing deployment access. Do not print environment secrets.

```sh
cat /etc/os-release
id vrioscu
sudo systemctl status vrioscu --no-pager
sudo systemctl cat vrioscu                 # inspect locally; redact any inline secrets
nginx -v
findmnt -T /var/lib
df -B1 /var/lib
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
```

Confirm the actual app account, existing server configs and the mount's EBS volume
mapping in EC2. The reported 47% usage does not identify free bytes or backup
headroom. If `/var/lib` is the root EBS filesystem, installers live on that volume
and share its capacity/failure domain. If a separate EBS volume is preferred,
mount it persistently at the chosen root (UUID in fstab), verify it is mounted
before service start, and add `RequiresMountsFor=/var/lib/vrioscu-releases` to the
service. Never silently upload into an unmounted replacement directory.

### Proposed Ubuntu directory setup

The shipped Nginx and systemd examples use **`/var/lib/vrioscu-releases`**. This
avoids changing access to `/var/lib/vrioscu`, where the database's parent is kept
private. Use these steps only after the checks above confirm this is appropriate.
Adapt account/group names to the actual installation.

```sh
sudo groupadd --system vrioscu-downloads    # skip if it already exists
sudo usermod -a -G vrioscu-downloads www-data
sudo install -d -o vrioscu -g vrioscu-downloads -m 2750 /var/lib/vrioscu-releases
sudo install -d -o vrioscu -g vrioscu-downloads -m 2750 /var/lib/vrioscu-releases/objects
sudo install -d -o vrioscu -g vrioscu-downloads -m 2700 /var/lib/vrioscu-releases/staging
sudo install -d -o vrioscu -g vrioscu -m 0700 /var/lib/vrioscu-releases/locks
sudo -u vrioscu test -w /var/lib/vrioscu-releases/staging
sudo -u www-data test -x /var/lib/vrioscu-releases/objects
```

Object files become 0640, owned by the app account, inheriting the download group
from the setgid staging directory (atomic placement keeps the same inode).
The staging group has no directory access. Uploaded files never receive execute
bits. Nginx can read objects but cannot write or list stages. Restart Nginx after
adding its supplementary group, then test a completed object's readability as
`www-data`. Do not make the root or object directory world-readable/writable.

Set in the existing `/etc/vrioscu/vrioscu.env` (edit securely, preserve secrets):

```ini
BASE_URL=https://vrioscu.com
RELEASE_STORAGE_PATH=/var/lib/vrioscu-releases
RELEASE_MAX_BYTES=2147483648
RELEASE_MIN_FREE_BYTES=1073741824
RELEASE_X_ACCEL=true
```

`DOWNLOAD_ALLOWED_HOSTS` continues to constrain legacy external links only.
No DNS changes are needed. Nginx's internal alias must exactly match this path.
`RELEASE_X_ACCEL=false` is the efficient Werkzeug file-wrapper/Range fallback
for environments without that Nginx internal location; never enable the flag
until the private alias is installed and tested.

### Proxy, migration and rollout

The Nginx example keeps normal forms at 64 KiB, permits only upload chunks up to
8 MiB, increases upload body/send timeouts to 180 seconds and upstream read
timeout to 300 seconds. Nginx buffering is bounded to one chunk. The Python
chunk endpoint alone receives the matching 8 MiB cap; metadata stays at 64 KiB.
Gunicorn timeout becomes 300 seconds for verification and slow chunks. Existing
workers remain loopback-only. The service sandbox adds the private storage root
to `ReadWritePaths`. The dedicated Nginx regex location is `internal`, has a
restricted generated filename pattern, rejects symlinks, and uses sendfile.

1. Back up the existing database and existing installer volume/files. Record
   capacity and installed versions. Keep a rollback code revision plus DB backup.
2. Provision and verify persistent storage; set the environment values above.
3. Deploy through the current GitHub → EC2 checkout workflow. Do not clean, move
   or replace `/var/lib/vrioscu-releases`. Binaries are ignored by Git and never
   belong under `/opt/vrioscu/app`, static, CI artifacts or a temporary directory.
4. Install/merge the changed Nginx, proxy and service settings into the actual
   configuration. For older Ubuntu Nginx versions replace `http2 on;` with
   `listen 443 ssl http2;` if `nginx -t` reports that directive unsupported.
   Avoid replacing local certificate or domain settings blindly.
5. `sudo nginx -t`, `sudo systemctl daemon-reload`, restart Nginx for new group
   membership and restart `vrioscu`. ExecStartPre/factory applies migrations.
   Confirm logs, public pages, admin login and a small draft upload first.
6. Publish an actual intended installer only after local review. Verify the
   certificate, attachment, bytes and Range over the deployed domain:

```sh
curl -I https://vrioscu.com/download/RELEASE_ID
curl -f -o /tmp/vrioscu-download-check.exe https://vrioscu.com/download/RELEASE_ID
sha256sum /tmp/vrioscu-download-check.exe    # compare internally with DB/build hash
curl -i -H 'Range: bytes=0-63' https://vrioscu.com/download/RELEASE_ID
curl -I https://vrioscu.com/_protected_installers/KNOWN_KEY.exe  # must return 404
sudo certbot certificates
sudo certbot renew --dry-run
```

Do not execute the downloaded installer on EC2. Remove the operator's temporary
verification copy afterward. For a missing/misconfigured certificate use the
existing Certbot/domain steps in `DEPLOYMENT.md`, validate ports 80/443 and
renewal, then repeat these checks. Wix A records alone do not install TLS.

## Backup, restoration and retention

The existing daily DB-only backup remains intact; it **does not back up binaries**.
Run the new consistent bundle backup after release changes or schedule it only
after budgeting destination capacity:

```sh
sudo -u vrioscu /opt/vrioscu/venv/bin/python /opt/vrioscu/app/scripts/backup_installers.py \
  --db /var/lib/vrioscu/vrioscu.db --storage /var/lib/vrioscu-releases \
  --dest /var/backups/vrioscu/installer-bundles
```

It uses SQLite online backup, integrity-checks the snapshot, copies every installer
referenced by that snapshot in 1 MiB blocks, verifies bytes/SHA, and writes a
manifest. Only a completed bundle becomes visible under its final name. It never
deletes original files or old bundles. Backups contain account data and internal
metadata: use private permissions and encrypted disks. A same-volume backup is
not recovery from volume loss. Use encrypted EBS snapshots of all relevant
volumes, or a direct encrypted transfer of completed bundles to a separate backup
host. No S3, CloudFront, Route 53 or external object storage is needed.

To restore a completed bundle:

1. Stop the app, keep a pre-restore DB and installer backup, and provision the
   private directory/mount and groups on the replacement instance.
2. Validate snapshot SQLite integrity and every `manifest.json` entry's safe key,
   exact size and SHA against its bundled file. Restore only generated keys into
   `objects`; never accept archive-supplied absolute paths or execute binaries.
3. Restore the bundle's `vrioscu.db` to the configured DATABASE_PATH, owned by
   `vrioscu`, mode 0600; remove stale WAL/SHM only while the app is stopped, using
   the existing restore procedure. Copy verified objects with no overwrite of
   different existing bytes, owner `vrioscu:vrioscu-downloads`, mode 0640.
4. Old incomplete transfers need not be restored. Run maintenance, migrate,
   restart, and check HTTPS download/Range and a sample SHA before opening traffic.

An instance replacement with the same retained/mounted EBS volume preserves the
files. Root-volume deletion on termination or volume loss destroys files unless
a separately retained snapshot/bundle exists. Record volume IDs, encryption,
DeleteOnTermination and snapshot retention in the operator runbook. Recovery
requires both the matching database and binaries, plus separately protected
application secrets/configuration. Keep the existing domain/DNS pointing to the
intended Elastic IP as in the current deployment process.

Monitor `df -B1`, `du -sh` for objects/staging/backups, and upload 507 responses.
Budget new installers, concurrent reservations, download copies and backups.
Review old release retention with the product owner. Unpublish before removing
download access; do not delete any binary referenced by a release or retained
backup. This implementation deliberately provides no automatic deletion of
published or formerly attached installers. Expand EBS/filesystem or remove
reviewed, backed-up unreferenced objects through a controlled operator procedure.

## Executed checks and limits

Local verification completed on 2026-10-12: the full regression suite passed
(one POSIX-permissions check is skipped on Windows); a real HTTP upload/download
of **214,958,203 bytes** passed with 26 chunks, retry, matching SHA-256, Range and
fresh-app persistence. Chromium also passed a 9 MiB transfer with a deliberately
lost acknowledgement, refresh/resume, draft then publish, Range, and layouts at
1440, 390 and 320 pixels with no overflow or JavaScript errors. A matching
database/installer bundle backup and restore passed in automated tests. The local
website database was backed up before applying migration 0006; no live database
was changed. A fresh app instance proves restart persistence; an actual EC2 Git
checkout replacement remains untested.

Reproducible checks:

```sh
python -m unittest discover -s tests -v
python scripts/check_large_upload.py
```

The opt-in integration creates inert PE-shaped fixture data, never runs it, uses
real localhost HTTP to transfer 205 MiB + 123 bytes, retries a chunk, verifies
durable offsets and final download SHA, exercises Range and a fresh application
instance against the same external database/storage. This proves local streaming
and restart persistence, not an actual EC2 deployment, browser transfer on a slow
WAN, Authenticode validity or Nginx configuration acceptance. See the completion
report for executed results. EC2 capacity/permissions, Nginx `-t`, real deployed
installer HTTPS/Range, cert renewal and actual checkout replacement remain
operator verification steps until live access is available.

References: [Nginx internal locations](https://nginx.org/en/docs/http/ngx_http_core_module.html#internal)
and [Werkzeug send_file](https://werkzeug.palletsprojects.com/en/stable/utils/#werkzeug.utils.send_file).
