"""Authenticated resumable transfers attached to the existing release catalog."""
from flask import Blueprint, abort, current_app, g, jsonify, request

from ..security import admin_required, check_rate
from ..services.installers import InstallerStore, upload_public

bp = Blueprint('uploads', __name__, url_prefix='/api/v1/admin/release-uploads')


def store():
    return InstallerStore(current_app.config['SETTINGS'])


@bp.post('')
@admin_required
def start():
    check_rate('upload_start', 20, 3600, key=str(g.user['id']))
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    return jsonify(upload_public(store().start(g.repos, g.user['id'], data.get('filename'), data.get('size')))), 201


@bp.get('/<upload_id>')
@admin_required
def status(upload_id):
    check_rate('upload_status', 300, 300, key=str(g.user['id']))
    return jsonify(upload_public(store().owned(g.repos, upload_id, g.user['id'])))


@bp.put('/<upload_id>')
@admin_required
def chunk(upload_id):
    check_rate('upload_chunk', 1200, 3600, key=str(g.user['id']))
    if request.mimetype != 'application/octet-stream':
        abort(415)
    try:
        offset = int(request.headers.get('Upload-Offset', ''))
    except ValueError:
        abort(400, description='A valid Upload-Offset header is required.')
    upload = store().chunk(g.repos, g.user['id'], upload_id, offset, request.stream, request.content_length)
    return jsonify(upload_public(upload))


@bp.post('/<upload_id>/complete')
@admin_required
def complete(upload_id):
    check_rate('upload_verify', 30, 3600, key=str(g.user['id']))
    try:
        result = store().complete(g.repos, g.user['id'], upload_id)
    except FileNotFoundError:
        abort(422, description='The saved upload is missing. Cancel this transfer and upload the installer again.')
    return jsonify(upload_public(result))


@bp.delete('/<upload_id>')
@admin_required
def cancel(upload_id):
    check_rate('upload_cancel', 60, 3600, key=str(g.user['id']))
    store().cancel(g.repos, upload_id, g.user['id'])
    return '', 204
