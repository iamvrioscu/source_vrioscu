"""JSON API v1. Same services and authorization as the HTML routes.

Authentication: the session cookie. Unsafe methods require the
X-CSRF-Token header (value from GET /api/v1/me or the page's meta tag).
"""
import logging

from flask import Blueprint, abort, current_app, g, jsonify, request, url_for

from ..db import transaction
from ..forms import FEEDBACK, PROFILE_UPDATE, SUPPORT
from ..logging_setup import log_event
from ..repositories.feedback import STATUSES as FEEDBACK_STATUSES
from ..repositories.releases import CHANNELS, PUBLIC_CHANNELS
from ..repositories.support import STATUSES as SUPPORT_STATUSES
from ..security import admin_required, check_rate, csrf_token, login_required
from ..services.auth import public_user
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
