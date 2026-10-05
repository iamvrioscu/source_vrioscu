"""Declarative input validation. Every write path runs through validate()."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                      r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{1,30})[A-Za-z0-9]$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]{1,32})?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(exe|msi|msix|zip)$")
NAME_RE = re.compile(r"^[^\x00-\x1f\x7f<>]{0,80}$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

COMMON_PASSWORDS = {
    "password1234", "123456789012", "qwertyuiopas", "passwordpassword", "letmein12345",
    "administrator", "welcome12345", "changeme1234", "vrioscu12345", "iloveyou1234",
}


class ValidationError(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__("validation failed")
        self.errors = errors


@dataclass
class F:
    """Field spec."""
    name: str
    label: str
    kind: str = "str"           # str|text|email|username|password|bool|int|choice|semver|sha256|https_url|filename|date
    required: bool = True
    max_len: int = 200
    min_len: int = 0
    choices: Iterable[str] | None = None
    min_value: int | None = None
    max_value: int | None = None
    check: Callable[[Any], str | None] | None = None
    extra: dict = field(default_factory=dict)


def _clean_str(raw: Any, multiline: bool) -> str:
    s = unicodedata.normalize("NFC", str(raw))
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    if not multiline:
        s = s.replace("\n", " ").replace("\t", " ")
    s = CONTROL_RE.sub("", s)
    return s.strip()


def https_url_ok(url: str, allowed_hosts: list[str] | None = None) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        return False
    host = p.hostname.lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local") or host.endswith(".localhost"):
        return False
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host):
        first = int(host.split(".")[0])
        second = int(host.split(".")[1])
        if first in (10, 127) or (first == 192 and second == 168) or (first == 172 and 16 <= second <= 31) \
                or (first == 169 and second == 254):
            return False
    if allowed_hosts and host not in allowed_hosts:
        return False
    return True


def validate(data: Mapping[str, Any], fields: list[F], *, allowed_hosts=None) -> dict:
    clean, errors = {}, {}
    for f in fields:
        raw = data.get(f.name)
        if f.kind == "bool":
            clean[f.name] = raw in (True, 1, "1", "true", "on", "yes")
            continue
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            if f.required:
                errors[f.name] = f"Enter {f.label.lower()}."
            else:
                clean[f.name] = None if f.kind == "int" else ""
            continue

        if f.kind == "password":
            value = str(raw)  # never normalise or strip secrets
            if len(value) < max(f.min_len, 1):
                errors[f.name] = f"{f.label} must be at least {f.min_len} characters."
            elif len(value) > f.max_len:
                errors[f.name] = f"{f.label} must be {f.max_len} characters or fewer."
            elif f.extra.get("strength") and value.lower() in COMMON_PASSWORDS:
                errors[f.name] = "Choose a less common password."
            else:
                clean[f.name] = value
            continue

        if f.kind == "int":
            try:
                value = int(str(raw).strip())
            except ValueError:
                errors[f.name] = f"{f.label} must be a whole number."
                continue
            if f.min_value is not None and value < f.min_value:
                errors[f.name] = f"{f.label} must be at least {f.min_value}."
                continue
            if f.max_value is not None and value > f.max_value:
                errors[f.name] = f"{f.label} must be at most {f.max_value}."
                continue
            clean[f.name] = value
            continue

        value = _clean_str(raw, multiline=f.kind == "text")
        if len(value) > f.max_len:
            errors[f.name] = f"{f.label} must be {f.max_len} characters or fewer."
            continue
        if len(value) < f.min_len:
            errors[f.name] = f"{f.label} must be at least {f.min_len} characters."
            continue

        error = None
        if f.kind == "email":
            value = value.lower()
            if len(value) > 254 or not EMAIL_RE.match(value):
                error = "Enter a valid email address, like name@example.com."
        elif f.kind == "username":
            if not USERNAME_RE.match(value):
                error = "Use 3 to 32 letters, numbers, dots, dashes or underscores."
        elif f.kind == "str":
            if f.extra.get("name") and not NAME_RE.match(value):
                error = f"{f.label} contains characters that aren't allowed."
        elif f.kind == "choice":
            if value not in set(f.choices or ()):
                error = f"Choose a valid {f.label.lower()}."
        elif f.kind == "semver":
            if not SEMVER_RE.match(value):
                error = f"{f.label} must look like 1.0.0."
        elif f.kind == "sha256":
            value = value.lower()
            if not SHA256_RE.match(value):
                error = "SHA-256 must be exactly 64 hexadecimal characters."
        elif f.kind == "https_url":
            if not https_url_ok(value, allowed_hosts if f.extra.get("restrict_hosts") else None):
                error = f"{f.label} must be a public https:// address" + (
                    " on an approved download host." if f.extra.get("restrict_hosts") and allowed_hosts else ".")
        elif f.kind == "filename":
            if not FILENAME_RE.match(value):
                error = "Use a plain file name ending in .exe, .msi, .msix or .zip, with no folders."
        elif f.kind == "date":
            try:
                date.fromisoformat(value)
            except ValueError:
                error = f"{f.label} must be a date in YYYY-MM-DD format."
        if error is None and f.check:
            error = f.check(value)
        if error:
            errors[f.name] = error
        else:
            clean[f.name] = value
    if errors:
        raise ValidationError(errors)
    return clean


def semver_tuple(v: str):
    m = SEMVER_RE.match(v or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups()[:3])
