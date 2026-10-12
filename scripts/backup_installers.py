#!/usr/bin/env python3
"""Consistent DB snapshot plus immutable referenced installers; no source deletes.

Run as the service account. Store completed bundles on a backed-up EBS volume
or copy them directly to a separately protected host. No object storage is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.installers import KEY, _sync_dir  # noqa: E402


def backup(db: Path, storage: Path, dest: Path) -> Path:
    if not db.is_file() or db.is_symlink() or storage.is_symlink():
        raise ValueError('Expected a private database and installer directory')
    dest.mkdir(parents=True, exist_ok=True, mode=0o700)
    if dest.is_symlink() or dest.resolve().is_relative_to(storage.resolve()):
        raise ValueError('Backup destination must be separate from installer storage')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    final = dest / ('installer-bundle-' + stamp)
    with tempfile.TemporaryDirectory(prefix='.installer-backup-',dir=dest) as temporary:
        work = Path(temporary)
        snapshot = work / 'vrioscu.db'
        source = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Database backup integrity check failed')
            records = target.execute('SELECT id,storage_key,file_size_bytes,sha256 FROM releases WHERE storage_key IS NOT NULL').fetchall()
        finally:
            source.close(); target.close()
        os.chmod(snapshot,0o600)
        with snapshot.open('r+b') as saved: os.fsync(saved.fileno())
        if shutil.disk_usage(dest).free < sum(r[2] for r in records) + 1024**3:
            raise ValueError('Insufficient space for the installer backup and 1 GiB reserve')
        objects = work / 'objects'; objects.mkdir(mode=0o700)
        manifest = []
        for rid,key,size,digest in records:
            if not KEY.fullmatch(key):
                raise ValueError('Unsafe stored installer key')
            original = storage / 'objects' / key
            if any(p.is_symlink() for p in (original,*original.parents)):
                raise ValueError('Refusing symbolic link in installer backup')
            sha = hashlib.sha256(); copied = 0
            with original.open('rb') as src, (objects / key).open('xb') as out:
                while block := src.read(1024**2):
                    out.write(block); sha.update(block); copied += len(block)
                out.flush(); os.fsync(out.fileno())
            os.chmod(objects/key,0o600)
            if copied != size or sha.hexdigest() != digest:
                raise ValueError('Installer backup verification failed')
            manifest.append({'release_id':rid,'storage_key':key,'bytes':size,'sha256':digest})
        with (work/'manifest.json').open('x',encoding='utf-8') as saved:
            saved.write(json.dumps({'created_at':stamp,'installers':manifest},indent=2)+'\n')
            saved.flush(); os.fsync(saved.fileno())
        os.chmod(work/'manifest.json',0o600)
        # A separate staging directory lets TemporaryDirectory clean up safely
        # while the completed bundle moves atomically to its permanent name.
        bundle = work/'bundle'; bundle.mkdir(mode=0o700)
        for item in (snapshot,objects,work/'manifest.json'):
            item.rename(bundle/item.name)
        _sync_dir(bundle/'objects')
        _sync_dir(bundle)
        bundle.rename(final)
        _sync_dir(dest)
    return final


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--storage',type=Path,required=True)
    parser.add_argument('--dest',type=Path,required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(backup(args.db.resolve(),args.storage,args.dest.resolve()))
