"""Central configuration.

Every product-facing value (name, version, channel, download details,
contacts) is defined here and nowhere else. Templates read it through the
`product` context variable; routes read it through `current_app.config`.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

INSECURE_SECRET_VALUES = {"", "change-me", "changeme", "secret", "dev", "development"}


class ConfigError(RuntimeError):
    """Raised when configuration is unsafe or incomplete."""


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _list(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if re.fullmatch(r"[A-Z_][A-Z0-9_]*", key):
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Product:
    name: str
    tagline: str
    positioning: str
    website_url: str
    version: str
    channel: str
    public_beta: bool
    windows_compatibility: str
    installer_signed: bool
    download_url: str
    release_notes_url: str
    installer_filename: str
    installer_sha256: str
    installer_size_bytes: int | None
    support_email: str
    privacy_email: str
    general_email: str
    privacy_notice_version: str

    @property
    def channel_label(self) -> str:
        return {"PUBLIC_BETA": "Public Beta", "STABLE": "Stable",
                "INTERNAL": "Internal", "DEV": "Development"}.get(self.channel, self.channel)


@dataclass
class Settings:
    env: str
    secret_key: str
    base_url: str
    database_path: Path
    trusted_proxy_count: int
    session_idle_minutes: int
    session_absolute_hours: int
    login_max_failures: int
    login_lock_minutes: int
    log_level: str
    cors_public_origins: list[str]
    download_allowed_hosts: list[str]
    product: Product
    extra: dict = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_test(self) -> bool:
        return self.env == "test"

    @property
    def https(self) -> bool:
        return self.base_url.startswith("https://")


def load_settings(overrides: dict | None = None) -> Settings:
    load_dotenv(BASE_DIR / ".env")
    overrides = overrides or {}
    env = overrides.get("env") or _env("APP_ENV", "development")

    db_raw = overrides.get("database_path") or _env("DATABASE_PATH", "instance/vrioscu.db")
    db_path = Path(db_raw)
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    base_url = (overrides.get("base_url") or _env("BASE_URL", "http://127.0.0.1:5000")).rstrip("/")
    size_raw = _env("INSTALLER_SIZE_BYTES")

    product = Product(
        name=_env("PRODUCT_NAME", "VRIOSCU"),
        tagline="Validate. Capture. Document.",
        positioning="Endpoint Validation & Evidence Capture",
        website_url=base_url,
        version=_env("PRODUCT_VERSION", "1.0.0"),
        channel=_env("RELEASE_CHANNEL", "PUBLIC_BETA"),
        public_beta=_bool("PUBLIC_BETA", True),
        windows_compatibility=_env("WINDOWS_COMPATIBILITY", "Windows 10 and Windows 11 (64-bit)"),
        installer_signed=_bool("INSTALLER_SIGNED", False),
        download_url=_env("DOWNLOAD_URL"),
        release_notes_url=_env("RELEASE_NOTES_URL"),
        installer_filename=_env("INSTALLER_FILENAME"),
        installer_sha256=_env("INSTALLER_SHA256").lower(),
        installer_size_bytes=int(size_raw) if size_raw.isdigit() else None,
        support_email=_env("SUPPORT_EMAIL"),
        privacy_email=_env("PRIVACY_EMAIL"),
        general_email=_env("GENERAL_EMAIL"),
        privacy_notice_version=_env("PRIVACY_NOTICE_VERSION", "2026-10-01"),
    )

    settings = Settings(
        env=env,
        secret_key=overrides.get("secret_key") or _env("SECRET_KEY"),
        base_url=base_url,
        database_path=db_path,
        trusted_proxy_count=_int("TRUSTED_PROXY_COUNT", 0),
        session_idle_minutes=_int("SESSION_IDLE_MINUTES", 60),
        session_absolute_hours=_int("SESSION_ABSOLUTE_HOURS", 12),
        login_max_failures=_int("LOGIN_MAX_FAILURES", 5),
        login_lock_minutes=_int("LOGIN_LOCK_MINUTES", 15),
        log_level=_env("LOG_LEVEL", "INFO").upper(),
        cors_public_origins=_list("CORS_PUBLIC_ORIGINS"),
        download_allowed_hosts=[h.lower() for h in _list("DOWNLOAD_ALLOWED_HOSTS")],
        product=product,
    )
    validate_settings(settings)
    return settings


def validate_settings(s: Settings) -> None:
    """Refuse to start with unsafe production configuration."""
    if s.env not in {"development", "test", "production"}:
        raise ConfigError("APP_ENV must be development, test or production")
    if s.product.channel not in {"PUBLIC_BETA", "STABLE", "INTERNAL", "DEV"}:
        raise ConfigError("RELEASE_CHANNEL is not a valid channel")
    if s.product.download_url and urlparse(s.product.download_url).scheme != "https":
        raise ConfigError("DOWNLOAD_URL must use https")
    if s.product.installer_sha256 and not re.fullmatch(r"[0-9a-f]{64}", s.product.installer_sha256):
        raise ConfigError("INSTALLER_SHA256 must be 64 hex characters")

    if s.is_production:
        if s.secret_key.lower() in INSECURE_SECRET_VALUES or len(s.secret_key) < 32:
            raise ConfigError("SECRET_KEY must be set to a random value of at least 32 characters")
        if not s.https:
            raise ConfigError("BASE_URL must use https in production")
        public_dirs = [BASE_DIR / "app" / "static"]
        for d in public_dirs:
            try:
                s.database_path.resolve().relative_to(d.resolve())
            except ValueError:
                continue
            raise ConfigError("DATABASE_PATH must not be inside a public/static directory")
    elif not s.secret_key:
        # Development convenience: a per-process random key. Sessions reset on restart.
        import secrets
        s.secret_key = secrets.token_urlsafe(48)
