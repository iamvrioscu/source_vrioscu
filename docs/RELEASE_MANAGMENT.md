# Release management

The website **publishes metadata about installers**. It does not host, build,
sign or execute them. Host the installer on HTTPS storage (for example a private S3 bucket behind CloudFront,
or a `downloads.` subdomain) and register it here.

## Release fields

| Field | Rule |
|---|---|
| Version | Semantic version `MAJOR.MINOR.PATCH[-pre]` |
| Channel | `PUBLIC_BETA`, `STABLE`, `INTERNAL`, `DEV` |
| Release date | `YYYY-MM-DD` |
| Release notes URL | Optional, public HTTPS |
| Download URL | Public HTTPS. Rejected: `http`, `file://`, UNC paths, localhost, private/link-local IPs, embedded credentials, and (if set) hosts outside `DOWNLOAD_ALLOWED_HOSTS` |
| Installer file name | Bare file name, `.exe`/`.msi`/`.msix`/`.zip`, no path separators |
| SHA-256 | 64 hex characters |
| File size | Bytes, > 0 |
| Mandatory | Release API reports `update_required: true` |
| Minimum supported version | Clients below it get `update_required: true`; can't exceed this release's version |
| Signed | Tick **only** if the file has a valid Authenticode signature. Shown publicly |
| Published | Drafts are invisible to the public |

`(version, channel)` is unique.

## Visibility by channel

| Channel | Download page | `/api/v1/releases*` | `/download/{id}` |
|---|---|---|---|
| PUBLIC_BETA | yes, when published | yes | yes |
| STABLE | yes, when published | yes | yes |
| INTERNAL | no | no (404) | no (404) |
| DEV | no | no (404) | no (404) |

The download page shows the latest published release for `RELEASE_CHANNEL`.
If none exists it falls back to the `DOWNLOAD_URL`/`INSTALLER_*` environment values,
and if those are empty it shows an honest "hasn't been published yet" state.

## Publishing a release

1. Build the installer (outside this system).
2. Compute the checksum on the build machine:
   `Get-FileHash -Algorithm SHA256 .\VRIOSCU-Setup-1.0.1.exe`
3. Upload to the HTTPS download host. Download it back and confirm the hash matches.
4. **Admin → Releases → Add release.** Fill in the fields; leave *Published* off.
5. Check the draft details, then edit and tick *Published*.
6. Verify: `/download` shows the version and checksum; `GET /api/v1/releases/latest` returns it.
7. Update `PRODUCT_VERSION` in `/etc/vrioscu/vrioscu.env` and restart so site-wide labels match.
8. Optionally export **subscribers** and email them.

Every create/update/delete is recorded in the audit log.

## Downloads

`/download/{id}` and `/download/latest` re-validate the stored URL, increment an
anonymous per-day counter (no IP or user stored) and redirect with `302`.
Counts appear in Admin → Releases and in the releases export.

## Desktop update check

```
GET https://vrioscu.com/api/v1/releases/latest?channel=PUBLIC_BETA&current_version=1.0.0
```

Returns version, checksum, size, signing status, `update_available`, `update_required`
and a `download_path`. The desktop application should verify the SHA-256 of
anything it downloads before use, and should present updates to the user, not
run them silently. The website never instructs a client to execute anything.

## Signing

The 1.0.0 Public Beta is unsigned, and the site says so. When a signed build exists:
set *Signed* on that release and `INSTALLER_SIGNED=true`. Never describe a build
as "Microsoft verified" or "Windows certified"; Authenticode signing is not certification.
