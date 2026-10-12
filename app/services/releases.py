"""Release metadata rules and download resolution."""
from __future__ import annotations

from ..repositories.releases import PUBLIC_CHANNELS
from ..validation import ValidationError, semver_tuple, https_url_ok
from flask import current_app
from .installers import InstallerStore

PUBLIC_RELEASE_FIELDS = ("version", "channel", "release_date", "release_notes_url", "installer_filename",
                         "sha256", "file_size_bytes", "is_mandatory", "minimum_supported_version",
                         "is_signed")


def check_release(data: dict) -> dict:
    data = dict(data)
    data["sha256"] = data.get("sha256") or None
    for k in ("is_mandatory", "is_signed", "is_published"):
        data[k] = 1 if data.get(k) else 0
    if data.get("minimum_supported_version"):
        if semver_tuple(data["minimum_supported_version"]) > semver_tuple(data["version"]):
            raise ValidationError({"minimum_supported_version":
                                   "Minimum supported version can't be newer than this release."})
    return data


def public_release(r: dict, download_path: str | None = None) -> dict:
    out = {k: r.get(k) for k in PUBLIC_RELEASE_FIELDS}
    for k in ("is_mandatory", "is_signed"):
        out[k] = bool(out[k])
    if download_path:
        out["download_path"] = download_path
    return out


def published_downloads(repos, allowed_hosts=None):
    return [r for r in repos.releases.list(channels=PUBLIC_CHANNELS,published_only=True)
            if (InstallerStore(current_app.config['SETTINGS']).available(r) if r.get('storage_key')
                else https_url_ok(r['download_url'],allowed_hosts or None))]


def channel_download(repos, channel, allowed_hosts=None):
    return next((r for r in published_downloads(repos,allowed_hosts) if r['channel']==channel),None)


def current_download(repos, product, allowed_hosts=None) -> dict | None:
    """Database publication is authoritative. Prefer configured public channel."""
    channel = product.channel if product.channel in PUBLIC_CHANNELS else "PUBLIC_BETA"
    candidates = published_downloads(repos,allowed_hosts)
    return next((r for r in candidates if r['channel']==channel),next(iter(candidates),None))


def human_size(n) -> str:
    if not n:
        return ""
    n = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
