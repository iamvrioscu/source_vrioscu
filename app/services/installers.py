"""Private, immutable installer storage. Never execute uploaded content.

Only generated identifiers reach filesystem operations. Per-upload OS locks work
across Gunicorn processes; SQLite records the durable committed byte offset.
"""
from __future__ import annotations

import hashlib
import errno
import os
import re
import shutil
import stat
import struct
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from werkzeug.exceptions import Conflict, HTTPException, NotFound, UnprocessableEntity

from ..config import ConfigError
from ..db import transaction
from ..time_utils import now_iso, utcnow, iso

CHUNK_BYTES = 8 * 1024 ** 2
BUFFER_BYTES = 1024 ** 2
UPLOAD_TTL_HOURS = 24
ID = re.compile(r'[0-9a-f]{32}')
KEY = re.compile(r'[0-9a-f]{32}\.exe')
FILENAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9 ._()-]{0,119}\.exe', re.IGNORECASE)


class InsufficientStorage(HTTPException):
    code = 507
    description = 'Insufficient installer storage.'


def filename_ok(value):
    if not isinstance(value, str) or FILENAME.fullmatch(value) is None or '..' in value:
        return False
    stem = value.split('.', 1)[0].rstrip(' ').upper()
    return stem not in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}


def _sync_dir(path):
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _open(path, flags, mode=0o600):
    if path.is_symlink():
        raise NotFound()
    return os.open(path, flags | getattr(os, 'O_NOFOLLOW', 0), mode)


class InstallerStore:
    def __init__(self, settings):
        self.s = settings
        self.root = settings.release_storage_path

    def prepare(self):
        # Production setup owns directory creation and group membership.
        for directory in (self.root, self.root / 'objects', self.root / 'staging', self.root / 'locks'):
            if directory.is_symlink() or any(p.is_symlink() for p in directory.parents):
                raise ConfigError('Installer storage cannot contain symbolic links')
            if self.s.is_production and not directory.is_dir():
                raise ConfigError('Installer storage is not provisioned; follow docs/INSTALLER_STORAGE.md')
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, key):
        if not isinstance(key, str) or KEY.fullmatch(key) is None:
            raise NotFound()
        path = self.root / 'objects' / key
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise NotFound()
        return path

    def stage(self, upload_id):
        if not isinstance(upload_id, str) or ID.fullmatch(upload_id) is None:
            raise NotFound()
        return self.root / 'staging' / (upload_id + '.part')

    @contextmanager
    def lock(self, upload_id):
        self.stage(upload_id)  # validate before constructing the lock filename
        self.prepare()
        path = self.root / 'locks' / (upload_id + '.lock')
        fd = _open(path, os.O_RDWR | os.O_CREAT)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b'0')
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise Conflict('This upload is busy. Retry in a moment.') from exc
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == 'nt':
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        # Retain tiny lock files: unlinking locks allows two processes to lock
        # different inodes for the same upload. They contain no installer bytes.

    def owned(self, repos, upload_id, owner):
        self.stage(upload_id)
        upload = repos.uploads.get(upload_id)
        if not upload or upload['owner_id'] != owner:
            raise NotFound()
        if upload['state'] == 'cancelled' or (upload['state'] != 'attached' and upload['expires_at'] < now_iso()):
            raise Conflict('This upload expired or was cancelled. Select the installer again.')
        return upload

    def start(self, repos, owner, filename, size):
        if not filename_ok(filename):
            raise UnprocessableEntity('Choose an .exe filename using letters, numbers, spaces, dots, dashes or parentheses (up to 124 characters).')
        if isinstance(size, bool) or not isinstance(size, int) or not 128 <= size <= self.s.release_max_bytes:
            raise UnprocessableEntity(f'Installer size must be between 128 and {self.s.release_max_bytes} bytes.')
        self.prepare()
        self.cleanup(repos)
        upload_id = uuid.uuid4().hex
        with transaction(repos.conn):
            if repos.uploads.active_count(owner) >= 3:
                raise Conflict('Finish or cancel an existing upload first (maximum three active uploads).')
            if shutil.disk_usage(self.root).free - repos.uploads.reservations() < size + self.s.release_min_free_bytes:
                raise InsufficientStorage('Insufficient installer storage. Free disk space or increase the persistent volume before retrying.')
            repos.uploads.create(upload_id, owner, filename, size, iso(utcnow() + timedelta(hours=UPLOAD_TTL_HOURS)))
        return repos.uploads.get(upload_id)

    def chunk(self, repos, owner, upload_id, offset, stream, length):
        if length is None or not 1 <= length <= CHUNK_BYTES:
            raise UnprocessableEntity(f'Each chunk must contain 1 to {CHUNK_BYTES} bytes.')
        with self.lock(upload_id):
            upload = self.owned(repos, upload_id, owner)
            committed = upload['received_bytes']
            if upload['state'] != 'uploading':
                raise Conflict('The upload has already been verified.')
            if offset < 0 or offset > committed or offset + length > upload['expected_bytes']:
                raise Conflict('Incorrect byte offset. Refresh upload status before retrying.')
            if offset < committed and offset + length > committed:
                raise Conflict('Retry must match a fully committed chunk.')
            if shutil.disk_usage(self.root).free < length + self.s.release_min_free_bytes:
                raise InsufficientStorage('Installer storage is full. No bytes from this chunk were committed.')
            path = self.stage(upload_id)
            fd = _open(path, os.O_RDWR | os.O_CREAT)
            with os.fdopen(fd, 'r+b') as file:
                if os.fstat(file.fileno()).st_size < committed:
                    raise Conflict('Saved upload is incomplete. Cancel and upload again.')
                file.truncate(committed)  # discard bytes left by a crashed request
                file.seek(offset)
                left = length
                try:
                    while left:
                        block = stream.read(min(BUFFER_BYTES, left))
                        if not block:
                            raise UnprocessableEntity('The chunk was interrupted. Retry from the saved offset.')
                        if offset < committed:
                            if file.read(len(block)) != block:
                                raise Conflict('Retried bytes do not match the saved chunk.')
                        else:
                            file.write(block)
                        left -= len(block)
                    file.flush()
                    os.fsync(file.fileno())
                    _sync_dir(path.parent)
                    if offset == committed:
                        with transaction(repos.conn):
                            repos.uploads.progress(upload_id, committed + length)
                except BaseException as exc:
                    file.truncate(committed)
                    file.flush()
                    os.fsync(file.fileno())
                    if isinstance(exc, OSError) and exc.errno in (errno.ENOSPC, getattr(errno,'EDQUOT',-1)):
                        raise InsufficientStorage('Installer storage filled during this chunk. Free space before retrying.') from exc
                    raise
            return repos.uploads.get(upload_id)

    def verify(self, path, size, digest=None):
        fd = _open(path, os.O_RDONLY)
        with os.fdopen(fd, 'rb') as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                raise UnprocessableEntity('Saved installer size does not match its metadata.')
            header = file.read(64)
            if len(header) < 64 or header[:2] != b'MZ':
                raise UnprocessableEntity('The uploaded file is not a Windows executable.')
            pe_offset = struct.unpack_from('<I', header, 60)[0]
            if not 64 <= pe_offset <= min(size - 6, BUFFER_BYTES):
                raise UnprocessableEntity('The Windows executable header is invalid.')
            file.seek(pe_offset)
            signature = file.read(6)
            if signature[:4] != b'PE\0\0' or signature[4:] not in (b'\x64\x86', b'\x4c\x01', b'\x64\xaa'):
                raise UnprocessableEntity('The Windows executable header is invalid.')
            file.seek(0)
            sha = hashlib.sha256()
            while block := file.read(BUFFER_BYTES):
                sha.update(block)
            result = sha.hexdigest()
            if digest and result != digest:
                raise UnprocessableEntity('Installer integrity verification failed. Upload the original file again.')
            return result

    def complete(self, repos, owner, upload_id):
        with self.lock(upload_id):
            upload = self.owned(repos, upload_id, owner)
            if upload['state'] in ('verified', 'attached'):
                self.verify(self.path(upload['storage_key']), upload['expected_bytes'], upload['sha256'])
                return upload
            if upload['received_bytes'] != upload['expected_bytes']:
                raise Conflict('Upload all installer bytes before verification.')
            key = upload_id + '.exe'
            final = self.path(key)
            stage = self.stage(upload_id)
            # Recovery after durable placement but before the DB commit.
            source = final if final.exists() else stage
            digest = self.verify(source, upload['expected_bytes'])
            if source == stage:
                os.chmod(stage, 0o640)  # service owner writes; download group only reads
                with os.fdopen(_open(stage, os.O_RDWR), 'r+b') as saved:
                    os.fsync(saved.fileno())
                # Hard linking is atomic and refuses replacement. Both directories
                # must be on the same persistent filesystem. No overwrite rename.
                os.link(stage, final, follow_symlinks=False)
                _sync_dir(final.parent)
                stage.unlink()
                _sync_dir(stage.parent)
            with transaction(repos.conn):
                repos.uploads.verified(upload_id, key, digest)
                repos.audit.record(owner, 'installer.verified', 'upload:' + upload_id, {'bytes': upload['expected_bytes']})
            return repos.uploads.get(upload_id)

    def available(self, release):
        try:
            info = self.path(release.get('storage_key')).stat()
            return stat.S_ISREG(info.st_mode) and info.st_size == release['file_size_bytes'] and bool(release.get('sha256'))
        except (OSError, NotFound):
            return False

    def cancel(self, repos, upload_id, owner=None):
        with self.lock(upload_id):
            with transaction(repos.conn):
                upload = repos.uploads.get(upload_id)
                if not upload or (owner is not None and upload['owner_id'] != owner):
                    raise NotFound()
                if upload['state'] == 'attached' or (upload['storage_key'] and repos.uploads.referenced(upload['storage_key'])):
                    raise Conflict('A release owns this installer. Unpublish or delete the release instead.')
                repos.uploads.cancel(upload_id)
                # Keep the DB lock until unlink completes; a concurrent release
                # attachment must see the cancelled state before using this file.
                for path in (self.stage(upload_id), self.path(upload_id + '.exe')):
                    if path.is_symlink():
                        raise NotFound()
                    path.unlink(missing_ok=True)
                    _sync_dir(path.parent)

    def cleanup(self, repos):
        count = 0
        for upload in repos.uploads.expired():
            try:
                self.cancel(repos, upload['id'])
                count += 1
            except Conflict:
                pass  # active request holds the lock; try next maintenance run
        return count


def upload_public(upload):
    return {k: upload[k] for k in ('id', 'original_filename', 'expected_bytes', 'received_bytes', 'state', 'expires_at')} | {'chunk_bytes': CHUNK_BYTES}
