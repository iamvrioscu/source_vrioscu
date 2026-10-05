"""Signed-in user area: profile, preferences, password, feedback, own-data export, deletion."""
import logging

from flask import Blueprint, Response, current_app, g, redirect, render_template, request, url_for

from ..db import transaction
from ..forms import CHANGE_PASSWORD, DELETE_ACCOUNT, FEEDBACK, PROFILE_UPDATE
from ..logging_setup import log_event
from ..security import check_rate, login_required
from ..services import auth as auth_service
from ..services.export import build_personal
from ..validation import ValidationError, validate

bp = Blueprint("account", __name__, url_prefix="/account")
log = logging.getLogger("vrioscu.account")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _render(template, **kw):
    kw.setdefault("noindex", True)
    return render_template(template, **kw)


@bp.route("", methods=["GET", "POST"])
@login_required
def profile():
    uid = g.user["id"]
    errors, saved = {}, request.args.get("saved") == "1"
    user = g.repos.users.get(uid)
    values = user
    if request.method == "POST":
        values = {**user, **request.form.to_dict()}
        try:
            data = validate(request.form, PROFILE_UPDATE)
            with transaction(g.db):
                if g.repos.users.exists(email=data["email"], exclude_id=uid):
                    raise ValidationError({"email": "Another account already uses this email."})
                g.repos.users.update_profile(uid, **data)
            log_event(log, logging.INFO, "account.profile_updated", user_id=uid)
            return redirect(url_for("account.profile", saved=1), 303)
        except ValidationError as e:
            errors = e.errors
    return _render("account/profile.html", page_title="Your profile", values=values, errors=errors,
                   saved=saved, welcome=request.args.get("welcome") == "1",
                   updates=g.repos.preferences.get_updates(uid)), (422 if errors else 200)


@bp.post("/preferences")
@login_required
def preferences():
    opted = request.form.get("product_updates") in ("1", "on", "true")
    s = current_app.config["SETTINGS"]
    with transaction(g.db):
        g.repos.preferences.set_updates(g.user["id"], opted, s.product.privacy_notice_version)
    log_event(log, logging.INFO, "account.updates_preference", user_id=g.user["id"], opted_in=opted)
    return redirect(url_for("account.profile", saved=1) + "#updates", 303)


@bp.route("/password", methods=["GET", "POST"])
@login_required
def password():
    errors, saved = {}, request.args.get("saved") == "1"
    if request.method == "POST":
        check_rate("password_change", 5, 900, key=str(g.user["id"]))
        try:
            data = validate(request.form, CHANGE_PASSWORD)
            auth_service.change_password(g.repos, g.user["id"], data["current_password"], data["new_password"],
                                         keep_session_id=g.session["id"])
            return redirect(url_for("account.password", saved=1), 303)
        except ValidationError as e:
            errors = e.errors
    return _render("account/password.html", page_title="Change password", errors=errors,
                   saved=saved), (422 if errors else 200)


@bp.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    errors, values, sent = {}, {}, request.args.get("sent") == "1"
    if request.method == "POST":
        check_rate("feedback", 10, 3600, key=str(g.user["id"]))
        values = request.form.to_dict()
        try:
            data = validate(request.form, FEEDBACK)
            with transaction(g.db):
                g.repos.feedback.create(user_id=g.user["id"], **data)
            log_event(log, logging.INFO, "feedback.created", user_id=g.user["id"], category=data["category"])
            return redirect(url_for("account.feedback", sent=1), 303)
        except ValidationError as e:
            errors = e.errors
    return _render("account/feedback.html", page_title="Send feedback", errors=errors, values=values, sent=sent,
                   history=g.repos.feedback.for_user(g.user["id"])), (422 if errors else 200)


@bp.route("/data", methods=["GET"])
@login_required
def data():
    return _render("account/data.html", page_title="Your data")


@bp.post("/data/export")
@login_required
def export_own():
    check_rate("self_export", 10, 3600, key=str(g.user["id"]))
    content, filename = build_personal(g.repos, g.user["id"])
    log_event(log, logging.INFO, "export.personal", user_id=g.user["id"])
    return Response(content, mimetype=XLSX, headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@bp.route("/delete", methods=["GET", "POST"])
@login_required
def delete():
    errors = {}
    if request.method == "POST":
        check_rate("account_delete", 5, 900, key=str(g.user["id"]))
        try:
            data = validate(request.form, DELETE_ACCOUNT)
            auth_service.delete_account(g.repos, g.user["id"], data["password"])
            g.clear_session_cookie = True
            g.user = g.session = None
            return redirect(url_for("public.home"), 303)
        except ValidationError as e:
            errors = e.errors
    return _render("account/delete.html", page_title="Delete account", errors=errors), (422 if errors else 200)
