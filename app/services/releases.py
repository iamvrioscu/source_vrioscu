"""Release metadata rules and download resolution."""
from __future__ import annotations

from ..repositories.releases import PUBLIC_CHANNELS
from ..validation import ValidationError, semver_tuple

PUBLIC_RELEASE_FIELDS = ("version", "channel", "release_date", "release_notes_url", "installer_filename",
                         "sha256", "file_size_bytes", "is_mandatory", "minimum_supported_version",
                         "is_signed")


def check_release(data: dict) -> dict:
    data = dict(data)
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


def current_download(repos, product) -> dict | None:
    """Published release for the configured channel, else the .env fallback, else None."""
    channel = product.channel if product.channel in PUBLIC_CHANNELS else "PUBLIC_BETA"
    rel = repos.releases.latest(channel)
    if rel:
        rel["source"] = "database"
        return rel
    if product.download_url:
        return {
            "id": None, "version": product.version, "channel": product.channel,
            "release_date": "", "release_notes_url": product.release_notes_url,
            "download_url": product.download_url, "installer_filename": product.installer_filename,
            "sha256": product.installer_sha256, "file_size_bytes": product.installer_size_bytes,
            "is_mandatory": 0, "minimum_supported_version": "", "is_signed": int(product.installer_signed),
            "source": "config",
        }
    return None


def human_size(n) -> str:
    if not n:
        return ""
    n = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
