from datetime import timedelta

from ..time_utils import iso, utcnow, parse_iso, ist_day_bounds, IST
from .base import rows


class AnalyticsRepository:
    """Consent-only, anonymous traffic. No account linkage, IP or full user agent."""
    def __init__(self, conn):
        self.conn = conn

    def record(self, visitor_id, event_id, path, referrer, browser, device, heartbeat=False, now=None):
        now = now or utcnow()
        ts = iso(now)
        if not heartbeat and self.conn.execute('SELECT 1 FROM analytics_views WHERE visitor_id=? AND event_id=?', (visitor_id, event_id)).fetchone():
            return False
        previous = self.conn.execute('SELECT id,last_seen_at FROM analytics_visits WHERE visitor_id=? ORDER BY id DESC LIMIT 1', (visitor_id,)).fetchone()
        if heartbeat:
            # Only an existing page-view event can refresh activity; idle pages cannot create visits.
            existing = self.conn.execute('SELECT visit_id FROM analytics_views WHERE visitor_id=? AND event_id=?', (visitor_id, event_id)).fetchone()
            if not previous or not existing or previous['id'] != existing['visit_id'] or parse_iso(previous['last_seen_at']) < now - timedelta(minutes=30):
                return False
        self.conn.execute('INSERT INTO analytics_visitors VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen_at=excluded.last_seen_at', (visitor_id, ts, ts))
        if previous and parse_iso(previous['last_seen_at']) >= now - timedelta(minutes=30):
            visit_id = previous['id']
            self.conn.execute('UPDATE analytics_visits SET last_seen_at=? WHERE id=?', (ts, visit_id))
        else:
            visit_id = self.conn.execute('INSERT INTO analytics_visits(visitor_id,started_at,last_seen_at,referrer,browser,device) VALUES(?,?,?,?,?,?)',
                                         (visitor_id, ts, ts, referrer, browser, device)).lastrowid
        if not heartbeat:
            self.conn.execute('INSERT INTO analytics_views(visit_id,visitor_id,event_id,path,created_at) VALUES(?,?,?,?,?)', (visit_id, visitor_id, event_id, path, ts))
        return True

    def forget(self, visitor_id):
        self.conn.execute('DELETE FROM analytics_visitors WHERE id=?', (visitor_id,))

    def active_visitors(self, now=None):
        return self.conn.execute('SELECT COUNT(*) FROM analytics_visitors WHERE last_seen_at >= ?',
                                 (iso((now or utcnow())-timedelta(minutes=5)),)).fetchone()[0]

    def purge(self, now=None):
        now = now or utcnow()
        last = self.conn.execute('SELECT cleaned_at FROM analytics_maintenance WHERE id=1').fetchone()
        if last and parse_iso(last[0]) > now - timedelta(days=1):
            return
        cutoff = iso(now - timedelta(days=90))
        self.conn.execute('DELETE FROM analytics_views WHERE created_at < ?', (cutoff,))
        self.conn.execute('DELETE FROM analytics_visits WHERE last_seen_at < ?', (cutoff,))
        self.conn.execute('DELETE FROM analytics_visitors WHERE last_seen_at < ?', (cutoff,))
        self.conn.execute('INSERT INTO analytics_maintenance VALUES(1,?) ON CONFLICT(id) DO UPDATE SET cleaned_at=excluded.cleaned_at', (iso(now),))

    def dashboard(self, days=7, now=None):
        now = now or utcnow()
        today = now.astimezone(IST).date()
        start, end = ist_day_bounds(today, days)
        def count(sql, params=()):
            return self.conn.execute(sql, params).fetchone()[0]
        metrics = {
            'active': self.active_visitors(now),
            'views': count('SELECT COUNT(*) FROM analytics_views WHERE created_at >= ? AND created_at < ?', (start,end)),
            'unique': count('SELECT COUNT(DISTINCT visitor_id) FROM analytics_views WHERE created_at >= ? AND created_at < ?', (start,end)),
            'visits': count('SELECT COUNT(*) FROM analytics_visits WHERE started_at >= ? AND started_at < ?', (start,end)),
        }
        for period in (1,7,30):
            bounds = ist_day_bounds(today,period)
            metrics[f'visits_{period}'] = count('SELECT COUNT(*) FROM analytics_visits WHERE started_at >= ? AND started_at < ?', bounds)
        popular = rows(self.conn.execute('SELECT path, COUNT(*) AS views,COUNT(DISTINCT visitor_id) AS visitors FROM analytics_views '
                                         'WHERE created_at >= ? AND created_at < ? GROUP BY path ORDER BY views DESC,path LIMIT 15', (start,end)))
        recent = rows(self.conn.execute('SELECT v.path,v.created_at,p.first_seen_at,p.last_seen_at,s.referrer,s.browser,s.device '
                                        'FROM analytics_views v JOIN analytics_visitors p ON p.id=v.visitor_id JOIN analytics_visits s ON s.id=v.visit_id '
                                        'WHERE v.created_at >= ? AND v.created_at < ? ORDER BY v.created_at DESC,v.id DESC LIMIT 50', (start,end)))
        daily = {r['day']:r['views'] for r in self.conn.execute("SELECT date(created_at,'+5 hours','+30 minutes') AS day,COUNT(*) AS views FROM analytics_views "
                                                              'WHERE created_at >= ? AND created_at < ? GROUP BY day', (start,end))}
        trend = [{'day':(today-timedelta(days=i)).isoformat(),'views':daily.get((today-timedelta(days=i)).isoformat(),0)} for i in range(days-1,-1,-1)]
        return dict(metrics=metrics, popular=popular, recent=recent, trend=trend, days=days, start=iso(parse_iso(start)), end=end)
