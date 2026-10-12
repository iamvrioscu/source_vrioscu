"""Administrator area. Every route is guarded server-side by @admin_required."""
import logging
import sqlite3
from werkzeug.exceptions import HTTPException

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
from ..services.installers import InstallerStore
from ..validation import F, ValidationError, validate

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
        "desktop_submissions_new": r.desktop_submissions.count("new"),
        "sessions": r.sessions.count_active(),
        "releases_published": len(r.releases.list(published_only=True)),
        "launch_interest": r.launch.count(status='registered'),
        "active_visitors": r.analytics.active_visitors(),
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


@bp.get("/desktop-submissions")
@admin_required
def desktop_submissions():
    status = request.args.get("status")
    if status and status not in ("new", "reviewed", "closed"):
        abort(400, description="Unknown desktop submission status.")
    items = g.repos.desktop_submissions.list(status=status, limit=200)
    return _render(
        "admin/desktop_submissions.html",
        page_title="Desktop submissions",
        items=items,
        status=status,
        statuses=("new", "reviewed", "closed"),
    )


@bp.post("/desktop-submissions/<int:item_id>")
@admin_required
def desktop_submission_status(item_id):
    status = request.form.get("status")
    if status not in ("new", "reviewed", "closed"):
        abort(400, description="Unknown desktop submission status.")
    with transaction(g.db):
        if not g.repos.desktop_submissions.set_status(item_id, status):
            abort(404)
        _audit(
            "desktop_submission.status",
            f"desktop_submission:{item_id}",
            status=status,
        )
    return redirect(
        url_for("admin.desktop_submissions", status=request.form.get("filter") or None),
        303,
    )


@bp.get("/subscribers")
@admin_required
def subscribers():
    return _render("admin/subscribers.html", page_title="Product-update subscribers",
                   items=g.repos.preferences.subscribers())


@bp.get('/analytics')
@admin_required
def analytics():
    try:
        days = int(request.args.get('days',7))
    except ValueError:
        abort(400)
    if days not in (1,7,30,90):
        abort(400)
    with transaction(g.db):
        g.repos.analytics.purge()
    return _render('admin/analytics.html',page_title='Visitor analytics',**g.repos.analytics.dashboard(days))


@bp.get('/launch-interest')
@admin_required
def launch_interest():
    q = request.args.get('q','').strip()[:100]
    status = request.args.get('status','')
    sort = request.args.get('sort','newest')
    if status not in ('','registered','unsubscribed') or sort not in ('newest','oldest','email'):
        abort(400)
    total = g.repos.launch.count(q,status)
    pages = max(1,-(-total // PAGE_SIZE))
    page = min(_page(),pages)
    return _render('admin/launch_interest.html',page_title='Launch Interest & Subscribers',
                   settings=g.repos.launch.settings(),items=g.repos.launch.list(q,status,sort,PAGE_SIZE,(page-1)*PAGE_SIZE),
                   total=total,page=page,pages=pages,q=q,status=status,sort=sort,errors={})


@bp.post('/launch-interest/settings')
@admin_required
def launch_settings():
    fields = [F('visible','Visibility',kind='bool'),F('registrations_enabled','Registrations',kind='bool'),
              F('heading','Heading',max_len=120),F('description','Description',kind='text',max_len=500),
              F('button_label','Button label',max_len=50),F('success_message','Success message',max_len=300)]
    try:
        data = validate(request.form,fields)
    except ValidationError as e:
        return _render('admin/launch_interest.html',page_title='Launch Interest & Subscribers',settings=request.form,
                       items=g.repos.launch.list(),total=g.repos.launch.count(),page=1,pages=max(1,-(-g.repos.launch.count() // PAGE_SIZE)),q='',status='',sort='newest',errors=e.errors),422
    with transaction(g.db):
        g.repos.launch.save_settings(data)
        _audit('launch.settings_updated','launch_settings:1',visible=data['visible'],registrations_enabled=data['registrations_enabled'])
    return redirect(url_for('admin.launch_interest',saved=1),303)


@bp.post('/launch-interest/<int:subscriber_id>/<action>')
@admin_required
def launch_manage(subscriber_id,action):
    if action not in ('unsubscribe','delete'):
        abort(404)
    with transaction(g.db):
        changed = getattr(g.repos.launch,action)(subscriber_id)
        if not changed:
            abort(404)
        _audit('launch.'+action,f'launch_subscriber:{subscriber_id}')
    return redirect(url_for('admin.launch_interest'),303)


@bp.get("/releases")
@admin_required
def releases():
    return _render("admin/releases.html", page_title="Releases", items=g.repos.releases.list(),
                   totals=g.repos.releases.download_totals())


def save_release(form, release_id=None):
    """Shared by HTML and API. Returns release id or raises ValidationError."""
    s = current_app.config["SETTINGS"]
    previous = g.repos.releases.get(release_id) if release_id else None
    if release_id and not previous:
        abort(404)
    if previous and request.endpoint == 'admin.release_edit' and not previous.get('storage_key'):
        form = {**{k: previous[k] for k in ('download_url','installer_filename','file_size_bytes')}, **form}
    upload_id = form.get('upload_id', '')
    local = bool(upload_id or (previous and previous.get('storage_key')))
    installer = InstallerStore(s)
    upload = None
    if upload_id:
        upload = installer.owned(g.repos, upload_id, g.user['id'])
        if upload['state'] != 'verified':
            raise ValidationError({'upload_id': 'Finish and verify the upload before saving the draft.'})
    if local:
        asset = ({'installer_filename': upload['original_filename'], 'file_size_bytes': upload['expected_bytes'],
                  'sha256': upload['sha256'], 'storage_key': upload['storage_key'], 'uploaded_at': upload['updated_at']}
                 if upload else {k: previous[k] for k in ('installer_filename','file_size_bytes','sha256','storage_key','uploaded_at')})
        data = check_release(validate(form, [f for f in RELEASE if f.name not in
                             ('download_url','installer_filename','file_size_bytes','sha256')], allowed_hosts=s.download_allowed_hosts))
        data.update(asset, download_url='')
        if upload and data['is_published']:
            raise ValidationError({'is_published': 'Save this verified installer as a draft first, then review and publish it.'})
        if upload or data['is_published']:
            try:
                installer.verify(installer.path(data['storage_key']), data['file_size_bytes'], data['sha256'])
            except (OSError, HTTPException) as exc:
                raise ValidationError({'upload_id': 'The saved installer failed verification. Upload it again before publishing.'}) from exc
    else:
        data = check_release(validate(form, RELEASE, allowed_hosts=s.download_allowed_hosts))
    with transaction(g.db):
        if upload:
            fresh = installer.owned(g.repos, upload_id, g.user['id'])
            if fresh['state'] != 'verified':
                raise ValidationError({'upload_id': 'This upload is already attached to a release.'})
        if release_id and not local and "sha256" not in form:
            previous = g.repos.releases.get(release_id) or abort(404)
            same_asset = all(data[key] == previous[key] for key in
                             ("version", "download_url", "installer_filename", "file_size_bytes"))
            # Retain recorded integrity metadata only while the installer identity is unchanged.
            data["sha256"] = previous["sha256"] if same_asset else None
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
            if upload:
                g.repos.uploads.attach(upload_id, release_id)
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
            if not request.form.get('upload_id'):
                raise ValidationError({'upload_id': 'Select, upload and verify an installer first.'})
            release_id = save_release(request.form)
            return redirect(url_for("admin.release_edit", release_id=release_id), 303)
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
