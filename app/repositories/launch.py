from ..time_utils import now_iso
from .base import row, rows

SETTING_FIELDS = ('visible', 'registrations_enabled', 'heading', 'description', 'button_label', 'success_message')


class LaunchRepository:
    def __init__(self, conn):
        self.conn = conn

    def settings(self):
        return row(self.conn.execute('SELECT * FROM launch_settings WHERE id = 1').fetchone())

    def save_settings(self, data):
        self.conn.execute('UPDATE launch_settings SET ' + ', '.join(f'{f} = ?' for f in SETTING_FIELDS)
                          + ', updated_at = ? WHERE id = 1', (*[data[f] for f in SETTING_FIELDS], now_iso()))

    def register(self, data, notice_version):
        ts = now_iso()
        # Duplicate submissions do not change consent, status, or identity information.
        return self.conn.execute(
            'INSERT INTO launch_subscribers(first_name,last_name,email,consent_granted,notice_version,registered_at,updated_at) '
            'VALUES (?,?,?,1,?,?,?) ON CONFLICT(email) DO NOTHING',
            (data['first_name'], data['last_name'], data['email'], notice_version, ts, ts)).rowcount

    def _where(self, search='', status=''):
        clauses, params = [], []
        if search:
            clauses.append('(first_name LIKE ? ESCAPE "\\" OR last_name LIKE ? ESCAPE "\\" OR email LIKE ? ESCAPE "\\")')
            escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            params.extend([f'%{escaped}%'] * 3)
        if status in ('registered', 'unsubscribed'):
            clauses.append('status = ?'); params.append(status)
        return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), params

    def count(self, search='', status=''):
        where, params = self._where(search, status)
        return self.conn.execute('SELECT COUNT(*) FROM launch_subscribers' + where, params).fetchone()[0]

    def list(self, search='', status='', sort='newest', limit=50, offset=0):
        where, params = self._where(search, status)
        order = {'newest': 'registered_at DESC, id DESC', 'oldest': 'registered_at, id', 'email': 'email, id'}.get(sort, 'registered_at DESC, id DESC')
        return rows(self.conn.execute('SELECT * FROM launch_subscribers' + where + ' ORDER BY ' + order + ' LIMIT ? OFFSET ?',
                                      (*params, min(limit, 100), max(offset, 0))))

    def unsubscribe(self, subscriber_id):
        return self.conn.execute("UPDATE launch_subscribers SET status='unsubscribed', consent_granted=0, updated_at=? WHERE id=?",
                                 (now_iso(), subscriber_id)).rowcount

    def export_rows(self, limit=100000):
        return rows(self.conn.execute('SELECT first_name,last_name,email,status,consent_granted,registered_at,confirmed_at FROM launch_subscribers ORDER BY registered_at DESC,id DESC LIMIT ?', (min(limit,100000),)))

    def delete(self, subscriber_id):
        return self.conn.execute('DELETE FROM launch_subscribers WHERE id=?', (subscriber_id,)).rowcount
