# Backup and restore

Direct uploads require **both database and installer backups**. The timer below
backs up the database only. See [INSTALLER_STORAGE.md](INSTALLER_STORAGE.md) for
the consistent installer bundle script, volume snapshots, restoration and
retention. A database restore alone cannot recover missing installer files.

## How backups work

`scripts/backup_db.py` uses SQLite's **online backup API**, so it produces a
consistent snapshot while the site is running. Copying the `.db` file with `cp`
while live is **not** safe in WAL mode; don't do it.

Each run:
1. Snapshots the database read-only into a temp file in the backup directory.
2. Runs `PRAGMA integrity_check`; aborts if it isn't `ok`.
3. Gzips to `vrioscu-YYYYMMDDTHHMMSSZ.db.gz`, mode `0600`, directory `0700`.
4. Deletes backups older than `--keep-days` (default 14).

Scheduled by `vrioscu-backup.timer` daily at 02:15 UTC, followed by `maintenance.py`
(purge expired sessions and stale rate-limit buckets, `PRAGMA optimize`, WAL checkpoint).

Manual run:

```bash
sudo systemctl start vrioscu-backup.service
ls -l /var/backups/vrioscu
```

Backups live in `/var/backups/vrioscu`, outside every web-served path. nginx
also denies `.db`, `.gz` and `.sql` requests outright.

## Off-host copies (recommended)

A backup on the same disk doesn't survive losing the instance. Options:

- **EBS snapshots** via Data Lifecycle Manager (whole volume, simplest).
- **Direct encrypted copies:** transfer completed DB/installer bundles to a
  separately protected backup host over the existing SSH backup workflow.
  This deployment does not require external object storage.

Backups contain personal data (accounts, emails, messages). Restrict access accordingly.

## Restore

```bash
sudo systemctl stop vrioscu
sudo -u vrioscu /opt/vrioscu/venv/bin/python /opt/vrioscu/app/scripts/restore_db.py \
     --backup /var/backups/vrioscu/vrioscu-20261005T021500Z.db.gz \
     --db /var/lib/vrioscu/vrioscu.db
sudo systemctl start vrioscu
curl -s http://127.0.0.1:8000/api/v1/health
```

`restore_db.py`:
- Refuses to run if the live database has an active WAL (app still running) unless `--force`.
- Decompresses to a temp file and integrity-checks it before touching anything.
- Moves the current database aside as `vrioscu.db.pre-restore-<timestamp>` (kept until you delete it).
- Removes stale `-wal`/`-shm` files and installs the restored file with mode `0600`.

If the backup is older than the code's schema, the app applies newer migrations on start.

## Test your restores

Monthly: restore the latest backup to a scratch path and count rows.

```bash
python3 scripts/restore_db.py --backup <file> --db /tmp/restore-test.db
sqlite3 /tmp/restore-test.db "PRAGMA integrity_check; SELECT COUNT(*) FROM users;"
rm /tmp/restore-test.db*
```

The round trip is also covered by `tests/test_backup.py`.
