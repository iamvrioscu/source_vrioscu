"""Public marketing, documentation, download and contact pages."""
from __future__ import annotations

import logging

from flask import Blueprint, Response, abort, current_app, g, redirect, render_template, request, url_for

from ..db import transaction
from ..forms import SUPPORT
from ..logging_setup import log_event
from ..repositories.releases import PUBLIC_CHANNELS
from ..security import check_rate
from ..services.releases import current_download
from ..validation import ValidationError, https_url_ok, validate

bp = Blueprint("public", __name__)
log = logging.getLogger("vrioscu.public")

PAGES = {
    # endpoint: (template, title, description)
    "home": ("public/home.html", None,
             "VRIOSCU is a Windows application that validates web endpoints, captures visual evidence and "
             "generates professional technical PDF reports."),
    "product": ("public/product.html", "Product",
                "What VRIOSCU is, who it is for, and how the Windows application and website work together."),
    "features": ("public/features.html", "Features",
                 "Validate endpoints, capture visual evidence, analyse technical results and document "
                 "everything in a professional report."),
    "how_it_works": ("public/how_it_works.html", "How it works",
                     "From configuration to reviewed report: the seven steps of a VRIOSCU validation run."),
    "use_cases": ("public/use_cases.html", "Use cases",
                  "How technical teams use VRIOSCU for site integrations, change verification, wireless "
                  "validation and support escalations."),
    "public_beta": ("public/public_beta.html", "Public Beta",
                    "VRIOSCU 1.0.0 Public Beta: what's included, what to expect and how to send feedback."),
    "documentation": ("public/documentation.html", "Documentation",
                      "Install VRIOSCU, run a validation and read the generated report."),
    "privacy": ("public/privacy.html", "Privacy",
                "What the VRIOSCU website collects, why, how long it is kept and how to contact us."),
}


def _page(endpoint):
    template, title, description = PAGES[endpoint]
    return render_template(template, page_title=title, meta_description=description)


@bp.get("/")
def home():
    return _page("home")


@bp.get("/product")
def product():
    return _page("product")


@bp.get("/features")
def features():
    return _page("features")


@bp.get("/how-it-works")
def how_it_works():
    return _page("how_it_works")


@bp.get("/use-cases")
def use_cases():
    return _page("use_cases")


@bp.get("/public-beta")
def public_beta():
    return _page("public_beta")


@bp.get("/documentation")
def documentation():
    return _page("documentation")


@bp.get("/privacy")
def privacy():
    return _page("privacy")


@bp.get("/download")
def download():
    s = current_app.config["SETTINGS"]
    release = current_download(g.repos, s.product)
    history = g.repos.releases.list(channels=PUBLIC_CHANNELS, published_only=True)
    return render_template("public/download.html", page_title="Download",
                           meta_description="Download the VRIOSCU Windows installer, verify its SHA-256 checksum "
                                            "and read the release notes.",
                           release=release, history=history)


def _redirect_to_installer(url: str):
    s = current_app.config["SETTINGS"]
    if not https_url_ok(url, s.download_allowed_hosts or None):
        log_event(log, logging.ERROR, "download.url_rejected")
        abort(404)
    resp = redirect(url, code=302)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/download/latest")
def download_latest():
    s = current_app.config["SETTINGS"]
    check_rate("download", 30, 300)
    release = current_download(g.repos, s.product)
    if not release:
        abort(404, description="No installer has been published yet.")
    if release.get("id"):
        with transaction(g.db):
            g.repos.releases.record_download(release["id"])
    return _redirect_to_installer(release["download_url"])


@bp.get("/download/<int:release_id>")
def download_release(release_id: int):
    check_rate("download", 30, 300)
    rel = g.repos.releases.get(release_id)
    if not rel or not rel["is_published"] or rel["channel"] not in PUBLIC_CHANNELS:
        abort(404)
    with transaction(g.db):
        g.repos.releases.record_download(rel["id"])
    return _redirect_to_installer(rel["download_url"])


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    errors, values, sent = {}, {}, request.args.get("sent") == "1"
    if g.user:
        values = {"name": f"{g.user['first_name']} {g.user['last_name']}".strip() or g.user["username"],
                  "email": g.user["email"]}
    if request.method == "POST":
        check_rate("contact", 5, 3600)
        values = request.form.to_dict()
        if values.get("website"):  # honeypot: humans never see this field
            log_event(log, logging.INFO, "support.honeypot")
            return redirect(url_for("public.contact", sent=1), 303)
        try:
            data = validate(values, SUPPORT)
            with transaction(g.db):
                rid = g.repos.support.create(user_id=(g.user or {}).get("id"), **data)
            log_event(log, logging.INFO, "support.created", request_id_db=rid, topic=data["topic"])
            return redirect(url_for("public.contact", sent=1), 303)
        except ValidationError as e:
            errors = e.errors
    return render_template("public/contact.html", page_title="Contact and support",
                           meta_description="Get help with installing VRIOSCU, your website account or your "
                                            "validation reports.",
                           errors=errors, values=values, sent=sent), (422 if errors else 200)


@bp.get("/robots.txt")
def robots():
    s = current_app.config["SETTINGS"]
    body = ("User-agent: *\nDisallow: /account\nDisallow: /admin\nDisallow: /api/\n"
            "Disallow: /login\nDisallow: /register\nDisallow: /download/\n"
            f"Sitemap: {s.base_url}/sitemap.xml\n")
    return Response(body, mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap():
    s = current_app.config["SETTINGS"]
    paths = ["/", "/product", "/features", "/how-it-works", "/use-cases", "/public-beta", "/download",
             "/documentation", "/privacy", "/contact"]
    urls = "".join(f"<url><loc>{s.base_url}{p}</loc></url>" for p in paths)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(xml, mimetype="application/xml")


@bp.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="img/favicon.svg"), 301)
