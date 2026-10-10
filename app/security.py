"""CSRF, rate limiting, security headers, access control, safe redirects."""
from __future__ import annotations

import hashlib
import hmac
import logging
import random
import secrets
import time
from functools import wraps
from urllib.parse import urlparse

from flask import abort, current_app, g, jsonify, redirect, request, url_for
from werkzeug.exceptions import HTTPException

from .db import transaction
from .logging_setup import log_event

log = logging.getLogger("vrioscu.security")

ANON_CSRF_COOKIE = "vr_csrf"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def settings():
    return current_app.config["SETTINGS"]


def digest(value: str, purpose: str) -> str:
    key = settings().secret_key.encode()
    return hmac.new(key, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def client_ip() -> str:
    return request.remote_addr or "unknown"


# ---------------------------------------------------------------- CSRF
def _csrf_binding() -> str:
    sess = getattr(g, "session", None)
    if sess:
        return "s:" + sess["csrf_secret"]
    if not getattr(g, "anon_csrf", None):
        g.anon_csrf = request.cookies.get(ANON_CSRF_COOKIE) or ""
        if len(g.anon_csrf) < 32:
            g.anon_csrf = secrets.token_urlsafe(32)
            g.set_anon_csrf = True
    return "a:" + g.anon_csrf


def csrf_token() -> str:
    return digest(_csrf_binding(), "csrf")



def verify_csrf() -> None:
    if request.method not in UNSAFE_METHODS:
        return

    # Defence in depth: browsers send Origin on cross-site unsafe requests.
    origin = request.headers.get("Origin")
    if origin and origin != "null":
        expected = urlparse(settings().base_url)
        got = urlparse(origin)
        if (
            (got.scheme, got.netloc) != (expected.scheme, expected.netloc)
            and got.netloc != request.host
        ):
            log_event(log, logging.WARNING, "csrf.origin_mismatch", path=request.path)
            abort(403, description="Cross-site request blocked.")

    # Desktop registration is a public JSON API, not a browser form.
    # Keep the origin check above and exempt only this exact endpoint.
    if request.method == "POST" and request.path == "/api/v1/users/register":
        if request.is_json:
            return

    # Desktop JSON updates authenticate through the bearer credential decorator.
    # Keep the Origin check above; only skip browser CSRF tokens for these exact routes.
    desktop_update_paths = {
        "/api/v1/users/username",
        "/api/v1/users/preferences",
    }
    authorization = request.headers.get("Authorization", "")
    scheme, _, raw_token = authorization.partition(" ")

    if (
        request.method == "PUT"
        and request.path in desktop_update_paths
        and request.is_json
        and scheme.lower() == "bearer"
        and bool(raw_token.strip())
        and len(raw_token.strip()) <= 256
    ):
        return

    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    if not sent or not hmac.compare_digest(sent, csrf_token()):
        log_event(log, logging.WARNING, "csrf.invalid", path=request.path)
        abort(400, description="Your form expired. Reload the page and try again.")



# ---------------------------------------------------------------- Rate limiting
class RateLimited(HTTPException):
    code = 429
    description = "Too many requests. Wait a moment and try again."

    def __init__(self, retry_after: int):
        super().__init__()
        self.retry_after = retry_after

    def get_headers(self, environ=None, scope=None):
        return [("Content-Type", "text/html; charset=utf-8"), ("Retry-After", str(self.retry_after))]


def check_rate(name: str, limit: int, window: int, key: str | None = None) -> None:
    """Fixed-window limiter backed by SQLite, so it holds across workers."""
    now = int(time.time())
    start = now - (now % window)
    bucket = digest(f"{name}|{key or client_ip()}|{window}", "rl")
    repos = g.repos
    with transaction(repos.conn):
        count = repos.rate_limits.hit(bucket, start)
        if random.random() < 0.02:
            repos.rate_limits.purge_before(now - 86400)
    if count > limit:
        log_event(log, logging.WARNING, "rate_limit.exceeded", limiter=name, path=request.path)
        raise RateLimited(retry_after=start + window - now)


def rate_limit(name: str, limit: int, window: int, methods=("POST",)):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if request.method in methods:
                check_rate(name, limit, window)
            return fn(*a, **kw)
        return wrapper
    return deco


# ---------------------------------------------------------------- Access control
def _wants_json() -> bool:
    return request.path.startswith("/api/")


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not getattr(g, "user", None):
            if _wants_json():
                return jsonify(error={"code": "unauthenticated", "message": "Sign in to continue."}), 401
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return fn(*a, **kw)
    return wrapper



def desktop_credential_required(fn):
    """Authenticate a desktop API request using a high-entropy bearer token."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        scheme, _, raw = header.partition(" ")
        if scheme.lower() != "bearer" or not raw or len(raw) > 256:
            return jsonify(error={
                "code": "unauthenticated",
                "message": "A valid desktop credential is required.",
                "request_id": g.get("request_id"),
            }), 401

        from .services.auth import token_hash

        credential = g.repos.desktop_credentials.get_active(token_hash(raw.strip()))
        if not credential:
            return jsonify(error={
                "code": "unauthenticated",
                "message": "A valid desktop credential is required.",
                "request_id": g.get("request_id"),
            }), 401

        with transaction(g.db):
            g.repos.desktop_credentials.touch(credential["id"])

        g.desktop_user = credential
        return fn(*args, **kwargs)

    return wrapper

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*a, **kw):
        if g.user.get("role") != "admin":
            log_event(log, logging.WARNING, "authz.denied", user_id=g.user["id"], path=request.path)
            abort(403)
        return fn(*a, **kw)
    return wrapper


def safe_next(target: str | None, default: str) -> str:
    """Only allow same-site relative paths as post-login redirect targets."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return default
    p = urlparse(target)
    if p.scheme or p.netloc:
        return default
    return target


# ---------------------------------------------------------------- Headers
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; "
       "base-uri 'self'; object-src 'none'; upgrade-insecure-requests")


def apply_security_headers(resp):
    s = settings()
    h = resp.headers
    h["Content-Security-Policy"] = CSP if s.https else CSP.replace("; upgrade-insecure-requests", "")
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    h["Cross-Origin-Resource-Policy"] = "same-origin"
    if s.https:
        h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if getattr(g, "user", None) or request.path.startswith(("/account", "/admin", "/api/v1/me", "/api/v1/admin")):
        h["Cache-Control"] = "no-store"
    h.pop("Server", None)
    return resp
