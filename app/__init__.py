"""VRIOSCU website application factory."""
from __future__ import annotations

import logging
import secrets
import time

import click
from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import security
from .config import load_settings
from .db import connect, migrate, transaction
from .logging_setup import configure_logging, log_event
from .reference_data import COUNTRIES, FEEDBACK_CATEGORIES, PURPOSES, SUPPORT_TOPICS, label_for
from .repositories import Repositories
from .services import auth as auth_service
from .services.releases import human_size

log = logging.getLogger("vrioscu.app")


def create_app(overrides: dict | None = None) -> Flask:
    settings = load_settings(overrides)
    configure_logging(settings.log_level, development=settings.env == "development")

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(
        SETTINGS=settings,
        SECRET_KEY=settings.secret_key,
        DEBUG=False,
        TESTING=settings.is_test,
        PROPAGATE_EXCEPTIONS=False,
        MAX_CONTENT_LENGTH=64 * 1024,          # forms and JSON only; no uploads
        JSON_SORT_KEYS=False,
        TEMPLATES_AUTO_RELOAD=settings.env == "development",
        SEND_FILE_MAX_AGE_DEFAULT=60 * 60 * 24 * 7,
    )
    app.json.sort_keys = False

    if settings.trusted_proxy_count:
        n = settings.trusted_proxy_count
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    migrate(settings.database_path)

    secure = settings.https
    cookie_name = "__Host-vr_session" if secure else "vr_session"
    app.config["SESSION_COOKIE_NAME_VR"] = cookie_name

    # ------------------------------------------------------------ lifecycle
    @app.before_request
    def _before():
        g.request_id = request.headers.get("X-Request-ID", "")[:64] or secrets.token_hex(8)
        g.started = time.perf_counter()
        g.db = connect(settings.database_path)
        g.repos = Repositories(g.db)
        g.user = g.session = None
        sess = auth_service.resolve_session(g.repos, request.cookies.get(cookie_name), settings)
        if sess:
            g.session = sess
            g.user = {"id": sess["user_id"], "username": sess["username"], "email": sess["email"],
                      "role": sess["role"], "first_name": sess["first_name"], "last_name": sess["last_name"]}
        elif request.cookies.get(cookie_name):
            g.clear_session_cookie = True
        if request.endpoint != "static":
            security.verify_csrf()

    @app.after_request
    def _after(resp):
        if getattr(g, "new_session_token", None):
            resp.set_cookie(cookie_name, g.new_session_token, httponly=True, secure=secure, samesite="Lax",
                            path="/", max_age=settings.session_absolute_hours * 3600)
        elif getattr(g, "clear_session_cookie", False):
            resp.delete_cookie(cookie_name, path="/", secure=secure, httponly=True, samesite="Lax")
        if getattr(g, "set_anon_csrf", False) and not getattr(g, "session", None):
            resp.set_cookie(security.ANON_CSRF_COOKIE, g.anon_csrf, httponly=True, secure=secure,
                            samesite="Lax", path="/", max_age=60 * 60 * 24)
        resp.headers["X-Request-ID"] = g.get("request_id", "")
        security.apply_security_headers(resp)
        if request.endpoint != "static":
            log_event(log, logging.INFO, "http.request", method=request.method, path=request.path,
                      status=resp.status_code, ms=round((time.perf_counter() - g.get("started", 0)) * 1000, 1),
                      user_id=(g.user or {}).get("id"), request_id=g.get("request_id"))
        return resp

    @app.teardown_request
    def _teardown(exc):
        db = g.pop("db", None)
        if db is not None:
            if db.in_transaction:
                db.execute("ROLLBACK")
            db.close()

    # ------------------------------------------------------------ templates
    @app.context_processor
    def _ctx():
        return {"product": settings.product, "current_user": g.get("user"), "csrf_token": security.csrf_token,
                "base_url": settings.base_url, "PURPOSES": PURPOSES, "COUNTRIES": COUNTRIES,
                "FEEDBACK_CATEGORIES": FEEDBACK_CATEGORIES, "SUPPORT_TOPICS": SUPPORT_TOPICS}

    app.jinja_env.globals["csrf_token"] = security.csrf_token  # visible inside imported macros
    app.jinja_env.filters["label_for"] = lambda key, choices: label_for(choices, key)
    app.jinja_env.filters["human_size"] = human_size
    app.jinja_env.filters["datetime"] = lambda v: (v or "").replace("T", " ").replace("Z", " UTC")
    app.jinja_env.filters["date"] = lambda v: (v or "")[:10]

    # ------------------------------------------------------------ blueprints
    from .routes.public import bp as public_bp
    from .routes.auth import bp as auth_bp
    from .routes.account import bp as account_bp
    from .routes.admin import bp as admin_bp
    from .routes.api import bp as api_bp
    for bp in (public_bp, auth_bp, account_bp, admin_bp, api_bp):
        app.register_blueprint(bp)

    # ------------------------------------------------------------ errors
    def _error(code: int, message: str, extra_headers=None):
        if request.path.startswith("/api/"):
            names = {400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found",
                     405: "method_not_allowed", 409: "conflict", 413: "payload_too_large",
                     415: "unsupported_media_type", 422: "validation_failed", 429: "rate_limited",
                     500: "server_error"}
            body = jsonify(error={"code": names.get(code, "error"), "message": message,
                                  "request_id": g.get("request_id")})
            resp = (body, code)
        else:
            template = f"errors/{code}.html" if code in (403, 404, 429, 500) else "errors/generic.html"
            resp = (render_template(template, code=code, message=message, request_id=g.get("request_id")), code)
        if extra_headers:
            return resp[0], resp[1], extra_headers
        return resp

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        headers = {"Retry-After": str(e.retry_after)} if isinstance(e, security.RateLimited) else None
        defaults = {400: "The request couldn't be processed. Check the form and try again.",
                    403: "You don't have access to this page.", 404: "This page doesn't exist.",
                    405: "That action isn't available here.", 413: "The request is too large.",
                    429: "Too many requests. Wait a moment and try again."}
        custom = e.description and e.description != type(e).description
        msg = e.description if custom else defaults.get(e.code, "The request couldn't be completed.")
        return _error(e.code or 500, msg, headers)

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        log.exception("unhandled_exception", extra={"fields": {"path": request.path,
                                                              "request_id": g.get("request_id")}})
        return _error(500, "Something went wrong on our side. The error has been logged.")

    # ------------------------------------------------------------ CLI
    @app.cli.command("init-db")
    def init_db():
        """Apply database migrations."""
        applied = migrate(settings.database_path)
        click.echo(f"Database ready at {settings.database_path} (applied: {', '.join(applied) or 'none'})")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin(username, email, password):
        """Create an administrator account, or promote an existing one."""
        from .forms import REGISTER
        from .validation import ValidationError, validate
        conn = connect(settings.database_path)
        repos = Repositories(conn)
        try:
            data = validate({"username": username, "email": email, "password": password,
                             "accept_privacy": True}, REGISTER)
            existing = repos.users.get_by_login(data["email"])
            if existing:
                with transaction(conn):
                    repos.users.set_role(existing["id"], "admin")
                    repos.audit.record(None, "admin.promoted_via_cli", f"user:{existing['id']}")
                click.echo(f"Promoted existing account {existing['username']} to administrator.")
                return
            uid = auth_service.register(repos, data, settings)
            with transaction(conn):
                repos.users.set_role(uid, "admin")
                repos.audit.record(None, "admin.created_via_cli", f"user:{uid}")
            click.echo(f"Administrator {data['username']} created.")
        except ValidationError as e:
            for field, msg in e.errors.items():
                click.echo(f"{field}: {msg}", err=True)
            raise SystemExit(1)
        finally:
            conn.close()

    log_event(log, logging.INFO, "app.started", env=settings.env, https=settings.https)
    return app
