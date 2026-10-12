"""Data-access layer. The only place SQL lives.

Each repository receives a DB-API connection and returns plain dicts.
Replacing SQLite with PostgreSQL means re-implementing these classes
(placeholder style, upsert syntax); services and routes stay unchanged.
"""
from .users import UserRepository
from .sessions import SessionRepository
from .desktop_credentials import DesktopCredentialRepository
from .desktop_submissions import DesktopSubmissionRepository
from .preferences import PreferenceRepository
from .feedback import FeedbackRepository
from .support import SupportRepository
from .releases import ReleaseRepository
from .rate_limits import RateLimitRepository
from .audit import AuditRepository
from .launch import LaunchRepository
from .analytics import AnalyticsRepository
from .uploads import UploadRepository


class Repositories:
    def __init__(self, conn):
        self.conn = conn
        self.users = UserRepository(conn)
        self.sessions = SessionRepository(conn)
        self.desktop_credentials = DesktopCredentialRepository(conn)
        self.desktop_submissions = DesktopSubmissionRepository(conn)
        self.preferences = PreferenceRepository(conn)
        self.feedback = FeedbackRepository(conn)
        self.support = SupportRepository(conn)
        self.releases = ReleaseRepository(conn)
        self.rate_limits = RateLimitRepository(conn)
        self.audit = AuditRepository(conn)
        self.launch = LaunchRepository(conn)
        self.analytics = AnalyticsRepository(conn)
        self.uploads = UploadRepository(conn)
