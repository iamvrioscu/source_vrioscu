"""Administrator area. Every route is guarded server-side by @admin_required."""
import logging
import sqlite3

from flask import Blueprint, Response, abort, current_app, g, redirect, render_template, request, url_for

from ..db import transaction
from ..forms import RELEASE
from ..logging_setup import log_event
from ..repositories.feedback import STATUSES as FEEDBACK_STATUSES
from ..repositories.releases import CHANNELS
from ..repositories.support import STATUSES as SUPPORT_STATUSES
from ..security import admin_required, check_rate
from ..services.export import DATASETS, build_dataset
from ..services.releases import check_release
from ..validation import ValidationError, validate

bp = Blueprint("admin", __name__, url_prefix="/admin")
log = logging.getLogger("vrioscu.admin")
PAGE_SIZE = 50
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _render(template, **kw):
    kw.setdefault("noindex", True)
    return render_template(template, **kw)


def _page():
    try:
        return max(1, int(request.args.get("page", 1)))
    except ValueError:
        return 1


def _audit(action, target="", **detail):
    g.repos.audit.record(g.user["id"], action, target, detail)
    log_event(log, logging.INFO, f"admin.{action}", actor=g.user["id"], target=target)


@bp.get("")
@admin_required
def dashboard():
    r = g.repos
    s = current_app.config["SETTINGS"]
    stats = {
        "users": r.users.count(), "subscribers": r.preferences.count_subscribers(),
        "feedback_new": r.feedback.count("new"), "support_new": r.support.count("new"),
        "sessions": r.sessions.count_active(),
        "releases_published": len(r.releases.list(published_only=True)),
    }
    status = {
        "environment": s.env, "https": s.https, "database": s.database_path.name,
        "migrations": [row[0] for row in g.db.execute("SELECT version FROM schema_migrations ORDER BY version")],
        "proxy_count": s.trusted_proxy_count,
    }
    return _render("admin/dashboard.html", page_title="Admin", stats=stats, status=status,
                   audit=r.audit.recent(15))


@bp.get("/users")
@admin_required
def users():
    q = request.args.get("q", "").strip()[:100]
    page = _page()
    total = g.repos.users.count(q)
    rows = g.repos.users.list(search=q, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
    return _render("admin/users.html", page_title="Users", users=rows, q=q, page=page, total=total,
                   pages=max(1, -(-total // PAGE_SIZE)))


@bp.post("/users/<int:user_id>/status")
@admin_required
def user_status(user_id):
    target = g.repos.users.get(user_id) or abort(404)
    if target["id"] == g.user["id"]:
        abort(400, description="You can't disable your own account.")
    active = request.form.get("active") == "1"
    with transaction(g.db):
        g.repos.users.set_active(user_id, active)
        if not active:
            g.repos.sessions.revoke_all_for_user(user_id)
        _audit("user.enabled" if active else "user.disabled", f"user:{user_id}")
    return redirect(url_for("admin.users", q=request.form.get("q", "")), 303)


@bp.route("/feedback", methods=["GET"])
@admin_required
def feedback():
    status = request.args.get("status")
    return _render("admin/feedback.html", page_title="Feedback", status=status, statuses=FEEDBACK_STATUSES,
                   items=g.repos.feedback.list(status=status, limit=200))


@bp.post("/feedback/<int:item_id>")
@admin_required
def feedback_status(item_id):
    status = request.form.get("status")
    if status not in FEEDBACK_STATUSES:
        abort(400)
    with transaction(g.db):
        if not g.repos.feedback.set_status(item_id, status):
            abort(404)
        _audit("feedback.status", f"feedback:{item_id}", status=status)
    return redirect(url_for("admin.feedback", status=request.form.get("filter") or None), 303)


@bp.get("/support")
@admin_required
def support():
    status = request.args.get("status")
    return _render("admin/support.html", page_title="Support requests", status=status, statuses=SUPPORT_STATUSES,
                   items=g.repos.support.list(status=status, limit=200))


@bp.post("/support/<int:item_id>")
@admin_required
def support_status(item_id):
    status = request.form.get("status")
    if status not in SUPPORT_STATUSES:
        abort(400)
    with transaction(g.db):
        if not g.repos.support.set_status(item_id, status):
            abort(404)
        _audit("support.status", f"support:{item_id}", status=status)
    return redirect(url_for("admin.support", status=request.form.get("filter") or None), 303)


@bp.get("/subscribers")
@admin_required
def subscribers():
    return _render("admin/subscribers.html", page_title="Product-update subscribers",
                   items=g.repos.preferences.subscribers())


@bp.get("/releases")
@admin_required
def releases():
    return _render("admin/releases.html", page_title="Releases", items=g.repos.releases.list(),
                   totals=g.repos.releases.download_totals())


def save_release(form, release_id=None):
    """Shared by HTML and API. Returns release id or raises ValidationError."""
    s = current_app.config["SETTINGS"]
    data = check_release(validate(form, RELEASE, allowed_hosts=s.download_allowed_hosts))
    with transaction(g.db):
        if g.repos.releases.exists(data["version"], data["channel"], exclude_id=release_id):
            raise ValidationError({"version": "This version already exists in that channel."})
        try:
            if release_id:
                g.repos.releases.update(release_id, data)
                _audit("release.updated", f"release:{release_id}", version=data["version"],
                       channel=data["channel"], published=data["is_published"])
            else:
                release_id = g.repos.releases.create(data, created_by=g.user["id"])
                _audit("release.created", f"release:{release_id}", version=data["version"],
                       channel=data["channel"], published=data["is_published"])
        except sqlite3.IntegrityError:
            raise ValidationError({"version": "This release conflicts with an existing record."})
    return release_id


@bp.route("/releases/new", methods=["GET", "POST"])
@admin_required
def release_new():
    errors, values = {}, {"channel": "PUBLIC_BETA"}
    if request.method == "POST":
        values = request.form.to_dict()
        try:
            save_release(request.form)
            return redirect(url_for("admin.releases"), 303)
        except ValidationError as e:
            errors = e.errors
    return _render("admin/release_form.html", page_title="New release", values=values, errors=errors,
                   channels=CHANNELS, release=None), (422 if errors else 200)


@bp.route("/releases/<int:release_id>", methods=["GET", "POST"])
@admin_required
def release_edit(release_id):
    rel = g.repos.releases.get(release_id) or abort(404)
    errors, values = {}, rel
    if request.method == "POST":
        values = request.form.to_dict()
        try:
            save_release(request.form, release_id)
            return redirect(url_for("admin.releases"), 303)
        except ValidationError as e:
            errors = e.errors
    return _render("admin/release_form.html", page_title=f"Edit release {rel['version']}", values=values,
                   errors=errors, channels=CHANNELS, release=rel), (422 if errors else 200)


@bp.post("/releases/<int:release_id>/delete")
@admin_required
def release_delete(release_id):
    with transaction(g.db):
        rel = g.repos.releases.get(release_id) or abort(404)
        g.repos.releases.delete(release_id)
        _audit("release.deleted", f"release:{release_id}", version=rel["version"], channel=rel["channel"])
    return redirect(url_for("admin.releases"), 303)


@bp.get("/exports")
@admin_required
def exports():
    return _render("admin/exports.html", page_title="Exports", datasets=DATASETS.values())


def export_response(dataset):
    if dataset not in DATASETS:
        abort(404)
    check_rate("admin_export", 30, 3600, key=str(g.user["id"]))
    content, filename, n = build_dataset(g.repos, dataset)
    with transaction(g.db):
        _audit("export.created", f"dataset:{dataset}", rows=n)
    return Response(content, mimetype=XLSX, headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@bp.post("/exports/<dataset>")
@admin_required
def export(dataset):
    return export_response(dataset)
