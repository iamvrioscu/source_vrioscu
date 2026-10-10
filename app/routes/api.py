"""JSON API v1. Same services and authorization as the HTML routes.

Authentication: the session cookie. Unsafe methods require the
X-CSRF-Token header (value from GET /api/v1/me or the page's meta tag).
"""
import logging
import secrets

from flask import Blueprint, abort, current_app, g, jsonify, request, url_for

from ..db import transaction
from ..forms import FEEDBACK, PROFILE_UPDATE, REGISTER, SUPPORT
from ..logging_setup import log_event
from ..repositories.feedback import STATUSES as FEEDBACK_STATUSES
from ..repositories.releases import CHANNELS, PUBLIC_CHANNELS
from ..repositories.support import STATUSES as SUPPORT_STATUSES
from ..security import admin_required, check_rate, csrf_token, desktop_credential_required, login_required
from ..services import auth as auth_service
from ..services.auth import hash_password, public_user, token_hash
from ..services.releases import current_download, public_release
from ..validation import ValidationError, semver_tuple, validate
from .admin import export_response, save_release

bp = Blueprint("api", __name__, url_prefix="/api/v1")
log = logging.getLogger("vrioscu.api")


def _json_body() -> dict:
    if not request.is_json:
        abort(415, description="Send a JSON body with Content-Type: application/json.")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400, description="The JSON body must be an object.")
    return body


def _invalid(e: ValidationError):
    return jsonify(error={"code": "validation_failed", "message": "Some fields need attention.",
                          "fields": e.errors, "request_id": g.get("request_id")}), 422


@bp.after_request
def _cors(resp):
    """CORS only for the public, read-only release endpoints, only for allowlisted origins."""
    origins = current_app.config["SETTINGS"].cors_public_origins
    origin = request.headers.get("Origin")
    if origin and origin in origins and request.method == "GET" and request.path.startswith("/api/v1/releases"):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
    return resp



# ---------------------------------------------------------------- desktop registration
@bp.put("/users/username")
@desktop_credential_required
def desktop_update_username():
    data = _json_body()
    if not isinstance(data.get("username"), str):
        return jsonify(error={
            "code": "validation_failed",
            "message": "A username is required.",
            "fields": {"username": "Enter a valid username."},
            "request_id": g.get("request_id"),
        }), 422

    username_field = next(
        (field for field in REGISTER if field.name == "username"), None
    )
    if username_field is None:
        raise RuntimeError("Username validation field is not configured.")

    try:
        clean = validate({"username": data["username"]}, [username_field])
    except ValidationError as exc:
        return _invalid(exc)

    username = clean["username"]
    user_id = g.desktop_user["user_id"]

    if g.repos.users.exists(username=username, exclude_id=user_id):
        return jsonify(error={
            "code": "validation_failed",
            "message": "That username is already taken.",
            "fields": {"username": "Choose another username."},
            "request_id": g.get("request_id"),
        }), 422

    try:
        with transaction(g.db):
            g.repos.users.update_username(user_id, username)
    except Exception as exc:
        # SQLite uniqueness is the final protection against concurrent requests.
        import sqlite3
        if isinstance(exc, sqlite3.IntegrityError):
            return jsonify(error={
                "code": "validation_failed",
                "message": "That username is already taken.",
                "fields": {"username": "Choose another username."},
                "request_id": g.get("request_id"),
            }), 422
        raise

    return jsonify(ok=True, username=username), 200


@bp.put("/users/preferences")
@desktop_credential_required
def desktop_update_preferences():
    data = _json_body()

    if not isinstance(data.get("product_updates"), bool):
        return jsonify(error={
            "code": "validation_failed",
            "message": "product_updates must be true or false.",
            "fields": {
                "product_updates": "Provide a boolean value."
            },
            "request_id": g.get("request_id"),
        }), 422

    enabled = data["product_updates"]
    user_id = g.desktop_user["user_id"]
    settings = current_app.config["SETTINGS"]

    with transaction(g.db):
        g.repos.preferences.set_updates(
            user_id,
            enabled,
            settings.product.privacy_notice_version,
        )

    return jsonify(ok=True, product_updates=enabled), 200


@bp.post("/users/register")
def desktop_register():
    check_rate("desktop_register", 5, 3600)
    data = _json_body()

    if data.get("accept_privacy") is not True:
        return jsonify(
            error={
                "code": "validation_failed",
                "message": "Privacy consent is required.",
                "fields": {"accept_privacy": "Privacy consent is required."},
                "request_id": g.get("request_id"),
            }
        ), 422

    fields = [f for f in REGISTER if f.name != "password"]
    try:
        clean = validate(data, fields)
    except ValidationError as exc:
        return _invalid(exc)

    required = ("username", "email", "first_name", "last_name", "country", "purpose")
    missing = [name for name in required if not clean.get(name)]
    if missing:
        return jsonify(
            error={
                "code": "validation_failed",
                "message": "Required registration fields are missing.",
                "fields": {name: "This field is required." for name in missing},
                "request_id": g.get("request_id"),
            }
        ), 422

    clean["accept_privacy"] = True
    clean["password"] = secrets.token_urlsafe(48)
    raw_credential = secrets.token_urlsafe(32)
    settings = current_app.config["SETTINGS"]

    try:
        with transaction(g.db):
            if g.repos.users.exists(username=clean["username"]):
                raise ValidationError({"username": "That username is taken. Choose another."})
            if g.repos.users.exists(email=clean["email"]):
                raise ValidationError({"email": "An account with this email already exists."})

            user_id = g.repos.users.create(
                username=clean["username"],
                email=clean["email"],
                password_hash=hash_password(clean["password"]),
                first_name=clean["first_name"],
                last_name=clean["last_name"],
                country=clean["country"],
                purpose=clean["purpose"],
            )

            version = settings.product.privacy_notice_version
            g.repos.preferences.record_consent(
                user_id, "privacy_notice", True, version
            )
            g.repos.preferences.set_updates(
                user_id, bool(clean.get("product_updates")), version
            )
            g.repos.desktop_credentials.create(
                user_id=user_id,
                token_hash=token_hash(raw_credential),
            )
    except ValidationError as exc:
        return _invalid(exc)

    log_event(log, logging.INFO, "desktop.registration_succeeded", user_id=user_id)
    return jsonify(
        ok=True,
        message="Registration successful.",
        user_id=user_id,
        desktop_credential=raw_credential,
    ), 201


# ---------------------------------------------------------------- public
@bp.get("/health")
def health():
    try:
        g.db.execute("SELECT 1").fetchone()
        return jsonify(status="ok")
    except Exception:
        log.exception("health.db_failed")
        return jsonify(status="degraded"), 503


@bp.get("/releases/latest")
def latest_release():
    check_rate("api_public", 120, 60)
    channel = request.args.get("channel", "PUBLIC_BETA").upper()
    if channel not in PUBLIC_CHANNELS:
        abort(404, description="Unknown or non-public channel.")
    rel = g.repos.releases.latest(channel)
    if not rel:
        abort(404, description="No published release in this channel.")
    out = public_release(rel, url_for("public.download_release", release_id=rel["id"]))
    current = request.args.get("current_version", "")
    if current:
        cur = semver_tuple(current)
        if not cur:
            abort(400, description="current_version must look like 1.0.0.")
        out["update_available"] = semver_tuple(rel["version"]) > cur
        out["update_required"] = bool(rel["is_mandatory"]) or bool(
            rel["minimum_supported_version"] and cur < semver_tuple(rel["minimum_supported_version"]))
    return jsonify(release=out)


@bp.get("/releases")
def list_releases():
    check_rate("api_public", 120, 60)
    items = g.repos.releases.list(channels=PUBLIC_CHANNELS, published_only=True)
    return jsonify(releases=[public_release(r, url_for("public.download_release", release_id=r["id"]))
                             for r in items])


@bp.post("/support")
def create_support():
    check_rate("contact", 5, 3600)
    try:
        data = validate(_json_body(), SUPPORT)
    except ValidationError as e:
        return _invalid(e)
    with transaction(g.db):
        rid = g.repos.support.create(user_id=(g.user or {}).get("id"), **data)
    return jsonify(support_request={"id": rid, "status": "new"}), 201


# ---------------------------------------------------------------- signed-in user
@bp.get("/me")
@login_required
def me():
    u = g.repos.users.get(g.user["id"])
    return jsonify(user=public_user(u), product_updates=g.repos.preferences.get_updates(u["id"]),
                   csrf_token=csrf_token())


@bp.patch("/me")
@login_required
def update_me():
    uid = g.user["id"]
    current = public_user(g.repos.users.get(uid))
    body = {**current, **_json_body()}
    try:
        data = validate(body, PROFILE_UPDATE)
        with transaction(g.db):
            if g.repos.users.exists(email=data["email"], exclude_id=uid):
                raise ValidationError({"email": "Another account already uses this email."})
            g.repos.users.update_profile(uid, **data)
    except ValidationError as e:
        return _invalid(e)
    return jsonify(user=public_user(g.repos.users.get(uid)))


@bp.put("/me/preferences")
@login_required
def update_preferences():
    body = _json_body()
    if not isinstance(body.get("product_updates"), bool):
        return _invalid(ValidationError({"product_updates": "Send true or false."}))
    with transaction(g.db):
        g.repos.preferences.set_updates(g.user["id"], body["product_updates"],
                                        current_app.config["SETTINGS"].product.privacy_notice_version)
    return jsonify(product_updates=body["product_updates"])


@bp.post("/feedback")
@login_required
def create_feedback():
    check_rate("feedback", 10, 3600, key=str(g.user["id"]))
    try:
        data = validate(_json_body(), FEEDBACK)
    except ValidationError as e:
        return _invalid(e)
    with transaction(g.db):
        fid = g.repos.feedback.create(user_id=g.user["id"], **data)
    return jsonify(feedback={"id": fid, "status": "new"}), 201


# ---------------------------------------------------------------- admin
def _paging():
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        abort(400, description="limit and offset must be integers.")
    return limit, offset


@bp.get("/admin/users")
@admin_required
def admin_users():
    limit, offset = _paging()
    q = request.args.get("q", "")[:100]
    items = g.repos.users.list(search=q, limit=limit, offset=offset)
    for u in items:
        u["is_active"], u["product_updates"] = bool(u["is_active"]), bool(u["product_updates"])
    return jsonify(users=items, total=g.repos.users.count(q), limit=limit, offset=offset)


@bp.get("/admin/feedback")
@admin_required
def admin_feedback():
    limit, offset = _paging()
    status = request.args.get("status")
    if status and status not in FEEDBACK_STATUSES:
        abort(400, description="Unknown status.")
    return jsonify(feedback=g.repos.feedback.list(status=status, limit=limit, offset=offset),
                   total=g.repos.feedback.count(status))


@bp.get("/admin/support")
@admin_required
def admin_support():
    limit, offset = _paging()
    status = request.args.get("status")
    if status and status not in SUPPORT_STATUSES:
        abort(400, description="Unknown status.")
    return jsonify(support_requests=g.repos.support.list(status=status, limit=limit, offset=offset),
                   total=g.repos.support.count(status))


def _admin_release(r):
    out = dict(r)
    for k in ("is_mandatory", "is_signed", "is_published"):
        out[k] = bool(out[k])
    return out


@bp.get("/admin/releases")
@admin_required
def admin_releases():
    return jsonify(releases=[_admin_release(r) for r in g.repos.releases.list(channels=CHANNELS)])


@bp.post("/admin/releases")
@admin_required
def admin_create_release():
    try:
        rid = save_release(_json_body())
    except ValidationError as e:
        return _invalid(e)
    return jsonify(release=_admin_release(g.repos.releases.get(rid))), 201


@bp.patch("/admin/releases/<int:release_id>")
@admin_required
def admin_update_release(release_id):
    rel = g.repos.releases.get(release_id) or abort(404)
    merged = {**rel, **_json_body()}
    try:
        save_release(merged, release_id)
    except ValidationError as e:
        return _invalid(e)
    return jsonify(release=_admin_release(g.repos.releases.get(release_id)))


@bp.delete("/admin/releases/<int:release_id>")
@admin_required
def admin_delete_release(release_id):
    with transaction(g.db):
        rel = g.repos.releases.get(release_id) or abort(404)
        g.repos.releases.delete(release_id)
        g.repos.audit.record(g.user["id"], "release.deleted", f"release:{release_id}", {"version": rel["version"]})
    return "", 204


@bp.post("/admin/exports/<dataset>")
@admin_required
def admin_export(dataset):
    return export_response(dataset)
