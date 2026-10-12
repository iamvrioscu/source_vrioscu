"""Public consent and launch forms; private data remains in admin routes."""
import secrets
import sqlite3
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, g, jsonify, redirect, render_template, request, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from ..db import transaction
from ..security import check_rate, digest
from ..validation import F, validate, ValidationError

bp = Blueprint('engagement', __name__)
TRACKED_PATHS = frozenset(('/', '/product', '/features', '/how-it-works', '/reports', '/documentation', '/use-cases', '/download', '/public-beta', '/contact', '/privacy'))
LAUNCH_FIELDS = [F('first_name','First name',max_len=80,extra={'name':True}),
                 F('last_name','Last name',max_len=80,extra={'name':True}), F('email','Email address',kind='email',max_len=254)]
COOKIE = 'vr_visitor'


def serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='analytics-visitor-v1')


def visitor():
    try:
        token = serializer().loads(request.cookies.get(COOKIE,''), max_age=30*86400)
        return digest(token, 'anonymous-visitor') if isinstance(token,str) and len(token)==43 else None
    except (BadSignature, SignatureExpired):
        return None


def tracking_blocked():
    return request.headers.get('DNT') == '1' or request.headers.get('Sec-GPC') == '1' or bool(g.user)


@bp.post('/privacy/analytics')
def analytics_consent():
    check_rate('analytics_consent',60,3600)
    choice = request.form.get('choice')
    if choice not in ('allow','decline'):
        abort(400)
    vid = visitor()
    if choice == 'allow' and tracking_blocked():
        choice = 'decline'
    resp = redirect(url_for('public.privacy'),303) if not request.headers.get('X-Requested-With') else jsonify(choice=choice)
    secure = current_app.config['SETTINGS'].https
    resp.set_cookie('vr_analytics', choice, max_age=180*86400, secure=secure, httponly=True, samesite='Lax')
    if choice == 'allow':
        if not vid:
            resp.set_cookie(COOKIE,serializer().dumps(secrets.token_urlsafe(32)),max_age=30*86400,secure=secure,httponly=True,samesite='Lax')
    else:
        if vid:
            with transaction(g.db):
                g.repos.analytics.forget(vid)
        resp.delete_cookie(COOKIE,secure=secure,httponly=True,samesite='Lax')
    return resp


@bp.post('/analytics/event')
def analytics_event():
    if request.cookies.get('vr_analytics') != 'allow' or tracking_blocked():
        return '',204
    vid = visitor()
    check_rate('analytics_event',180,300,key=vid)
    data = request.get_json(silent=True) or {}
    if not isinstance(data,dict):
        abort(400)
    fresh = None
    if not vid:
        fresh = secrets.token_urlsafe(32)
        vid = digest(fresh,'anonymous-visitor')
    path, event = data.get('path'), data.get('event_id')
    if not isinstance(path,str) or path not in TRACKED_PATHS or data.get('kind','view') not in ('view','heartbeat') or not isinstance(event,str) or not (16 <= len(event) <= 64) or not event.isascii() or not event.replace('-','').isalnum():
        abort(400)
    agent = request.user_agent.string.lower()
    browser = next((label for needle,label in [('edg/','Edge'),('firefox/','Firefox'),('chrome/','Chrome'),('safari/','Safari')] if needle in agent),'Other')
    device = 'Tablet' if 'ipad' in agent or ('android' in agent and 'mobile' not in agent) else ('Mobile' if 'mobile' in agent else 'Desktop')
    try:
        ref = urlparse(str(data.get('referrer',''))[:2048])
        referrer = ref.hostname if ref.scheme in ('http','https') else None
    except ValueError:
        referrer = None
    if referrer == request.host.split(':')[0]:
        referrer = 'Internal'
    with transaction(g.db):
        g.repos.analytics.purge()
        g.repos.analytics.record(vid,event,path,(referrer or 'Direct')[:253],browser,device,heartbeat=data.get('kind')=='heartbeat')
    resp = current_app.make_response(('',204))
    if fresh:
        resp.set_cookie(COOKIE,serializer().dumps(fresh),max_age=30*86400,secure=current_app.config['SETTINGS'].https,httponly=True,samesite='Lax')
    return resp


@bp.post('/launch-interest')
def launch_interest():
    check_rate('launch_interest',5,3600)
    errors, values = {}, request.form.to_dict()
    settings = g.repos.launch.settings()
    if not settings['registrations_enabled']:
        return render_template('public/launch_result.html',page_title='Launch interest',closed=True),403
    try:
        data = validate(values,LAUNCH_FIELDS)
        if values.get('consent') != '1':
            raise ValidationError({'consent':'Choose whether to receive VRIOSCU launch news before joining.'})
        if values.get('website'):
            raise ValidationError({'form':'This registration could not be accepted.'})
        with transaction(g.db):
            # Re-check in the write transaction so a simultaneous settings change is respected.
            if not g.repos.launch.settings()['registrations_enabled']:
                abort(403,description='Launch registrations are closed.')
            g.repos.launch.register(data,current_app.config['SETTINGS'].product.privacy_notice_version)
        return redirect(url_for('engagement.launch_saved'),303)
    except ValidationError as e:
        errors = e.errors
    except sqlite3.Error:
        current_app.logger.exception('launch.persist_failed')
        return render_template('public/launch_result.html',page_title='Launch interest',save_failed=True),503
    return render_template('public/launch_result.html',page_title='Launch interest',errors=errors,values=values),422


@bp.get('/launch-interest/saved')
def launch_saved():
    return render_template('public/launch_result.html',page_title='Launch interest',saved=True)
