"""Sign in, create account, sign out."""
from flask import Blueprint, current_app, g, redirect, render_template, request, url_for

from ..forms import LOGIN, REGISTER
from ..security import check_rate, login_required, safe_next
from ..services import auth as auth_service
from ..validation import ValidationError, validate

bp = Blueprint("auth", __name__)


def _settings():
    return current_app.config["SETTINGS"]


def _begin(user_id, default):
    g.new_session_token = auth_service.start_session(g.repos, user_id, _settings())
    if g.session:  # rotate: never carry a prior session across a login
        auth_service.end_session(g.repos, g.session["id"], g.session["user_id"])
    return redirect(safe_next(request.args.get("next") or request.form.get("next"), default), 303)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user and request.method == "GET":
        return redirect(url_for("account.profile"))
    errors, form_error, values = {}, None, {}
    if request.method == "POST":
        check_rate("login_ip", 20, 600)
        values = {"identifier": request.form.get("identifier", "")}
        try:
            data = validate(request.form, LOGIN)
            check_rate("login_account", 10, 600, key=data["identifier"].lower())
            user = auth_service.authenticate(g.repos, data["identifier"], data["password"], _settings())
            return _begin(user["id"], url_for("admin.dashboard") if user["role"] == "admin"
                          else url_for("account.profile"))
        except ValidationError as e:
            errors = e.errors
        except auth_service.AuthError as e:
            form_error = e.message
    status = 401 if form_error else (422 if errors else 200)
    return render_template("auth/login.html", page_title="Sign in", errors=errors, form_error=form_error,
                           values=values, next=request.args.get("next", ""), noindex=True), status


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user and request.method == "GET":
        return redirect(url_for("account.profile"))
    errors, values = {}, {}
    if request.method == "POST":
        check_rate("register", 5, 3600)
        values = {k: v for k, v in request.form.items() if "password" not in k}
        try:
            data = validate(request.form, REGISTER)
            uid = auth_service.register(g.repos, data, _settings())
            return _begin(uid, url_for("account.profile", welcome=1))
        except ValidationError as e:
            errors = e.errors
    return render_template("auth/register.html", page_title="Create account", errors=errors, values=values,
                           noindex=True), (422 if errors else 200)


@bp.post("/logout")
@login_required
def logout():
    auth_service.end_session(g.repos, g.session["id"], g.user["id"])
    g.clear_session_cookie = True
    g.session = g.user = None
    return redirect(url_for("public.home"), 303)
