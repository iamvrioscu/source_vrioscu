"""Accounts, credentials and sessions."""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from ..db import transaction
from ..logging_setup import log_event
from ..time_utils import iso, parse_iso, plus, utcnow
from ..validation import ValidationError

log = logging.getLogger("vrioscu.auth")

HASH_METHOD = "scrypt:32768:8:1"
# Used to equalise timing when the account does not exist.
_DUMMY_HASH = generate_password_hash("not-a-real-password-" + secrets.token_hex(8), method=HASH_METHOD)


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def hash_password(pw: str) -> str:
    return generate_password_hash(pw, method=HASH_METHOD)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _password_rules(pw: str, username: str, email: str, field="password"):
    lowered = pw.lower()
    local_part = (email or "").split("@")[0].lower()
    for ident in (username.lower() if username else "", local_part):
        if len(ident) >= 4 and ident in lowered:
            raise ValidationError({field: "Your password can't contain your username or email name."})


def register(repos, data: dict, settings) -> int:
    if not data.get("accept_privacy"):
        raise ValidationError({"accept_privacy": "Confirm you have read the privacy notice to create an account."})
    _password_rules(data["password"], data["username"], data["email"])
    with transaction(repos.conn):
        if repos.users.exists(username=data["username"]):
            raise ValidationError({"username": "That username is taken. Choose another."})
        if repos.users.exists(email=data["email"]):
            # Same wording as a generic failure would leak less, but users need to know
            # to sign in instead. Registration is rate limited to limit enumeration.
            raise ValidationError({"email": "An account with this email already exists. Sign in instead."})
        user_id = repos.users.create(
            username=data["username"], email=data["email"], password_hash=hash_password(data["password"]),
            first_name=data.get("first_name", ""), last_name=data.get("last_name", ""),
            country=data.get("country", ""), purpose=data.get("purpose", ""))
        v = settings.product.privacy_notice_version
        repos.preferences.record_consent(user_id, "privacy_notice", True, v)
        repos.preferences.set_updates(user_id, bool(data.get("product_updates")), v)
    log_event(log, logging.INFO, "auth.registered", user_id=user_id)
    return user_id


def authenticate(repos, identifier: str, password: str, settings) -> dict:
    generic = AuthError("invalid_credentials", "Email/username or password is incorrect.")
    user = repos.users.get_by_login(identifier.strip())
    if not user:
        check_password_hash(_DUMMY_HASH, password)
        log_event(log, logging.INFO, "auth.login_failed", reason="unknown_account")
        raise generic
    locked = parse_iso(user["locked_until"])
    if locked and locked > utcnow():
        log_event(log, logging.WARNING, "auth.login_locked", user_id=user["id"])
        raise AuthError("locked", "Too many failed attempts. Try again in a few minutes.")
    if not check_password_hash(user["password_hash"], password):
        with transaction(repos.conn):
            repos.users.record_failure(user["id"], settings.login_max_failures,
                                       plus(minutes=settings.login_lock_minutes))
        log_event(log, logging.INFO, "auth.login_failed", user_id=user["id"], reason="bad_password")
        raise generic
    if not user["is_active"]:
        log_event(log, logging.WARNING, "auth.login_inactive", user_id=user["id"])
        raise generic
    with transaction(repos.conn):
        repos.users.record_success(user["id"])
    log_event(log, logging.INFO, "auth.login_ok", user_id=user["id"])
    return user


def start_session(repos, user_id: int, settings) -> str:
    raw = secrets.token_urlsafe(32)
    with transaction(repos.conn):
        repos.sessions.create(token_hash=token_hash(raw), user_id=user_id,
                              csrf_secret=secrets.token_urlsafe(32),
                              expires_at=plus(hours=settings.session_absolute_hours))
        repos.sessions.purge_expired()
    return raw


def resolve_session(repos, raw: str | None, settings) -> dict | None:
    if not raw or len(raw) > 128:
        return None
    sess = repos.sessions.get_active(token_hash(raw))
    if not sess:
        return None
    if not sess["is_active"]:
        return None
    last = parse_iso(sess["last_seen_at"])
    now = utcnow()
    if last and now - last > timedelta(minutes=settings.session_idle_minutes):
        with transaction(repos.conn):
            repos.sessions.revoke(sess["id"])
        log_event(log, logging.INFO, "auth.session_idle_expired", user_id=sess["user_id"])
        return None
    if last and now - last > timedelta(seconds=60):
        with transaction(repos.conn):
            repos.sessions.touch(sess["id"])
    return sess


def end_session(repos, session_id: int, user_id: int) -> None:
    with transaction(repos.conn):
        repos.sessions.revoke(session_id)
    log_event(log, logging.INFO, "auth.logout", user_id=user_id)


def change_password(repos, user_id: int, current: str, new: str, keep_session_id: int) -> None:
    user = repos.users.get(user_id)
    if not check_password_hash(user["password_hash"], current):
        raise ValidationError({"current_password": "Current password is incorrect."})
    if current == new:
        raise ValidationError({"new_password": "Choose a password you haven't used for this account."})
    _password_rules(new, user["username"], user["email"], field="new_password")
    with transaction(repos.conn):
        repos.users.set_password(user_id, hash_password(new))
        repos.sessions.revoke_all_for_user(user_id, except_id=keep_session_id)
    log_event(log, logging.INFO, "auth.password_changed", user_id=user_id)


def delete_account(repos, user_id: int, password: str) -> None:
    user = repos.users.get(user_id)
    if not check_password_hash(user["password_hash"], password):
        raise ValidationError({"password": "Password is incorrect."})
    with transaction(repos.conn):
        if user["role"] == "admin" and repos.users.count_admins() <= 1:
            raise ValidationError({"password": "This is the only administrator account. "
                                               "Add another administrator before deleting it."})
        repos.users.delete(user_id)
        repos.audit.record(None, "account.self_deleted", f"user:{user_id}")
    log_event(log, logging.INFO, "auth.account_deleted", user_id=user_id)


def public_user(u: dict) -> dict:
    """Output allowlist: the only user fields ever serialised to clients."""
    return {k: u.get(k) for k in ("id", "username", "email", "first_name", "last_name",
                                  "country", "purpose", "role", "created_at", "last_login_at")}
