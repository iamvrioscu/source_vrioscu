import os
import re
import shutil
import tempfile
import unittest

os.environ.setdefault("LOG_LEVEL", "CRITICAL")

from app import create_app  # noqa: E402
from app.db import connect, transaction  # noqa: E402
from app.repositories import Repositories  # noqa: E402

PASSWORD = "correct horse battery"
SHA = "a" * 64


class AppTestCase(unittest.TestCase):
    base_url = "http://localhost"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vrioscu-test-")
        self.db_path = os.path.join(self.tmp, "test.db")
        self.app = create_app({"env": "test", "database_path": self.db_path, "base_url": self.base_url,
                               "secret_key": "t" * 48})
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ helpers
    def repos(self):
        conn = connect(self.app.config["SETTINGS"].database_path)
        return conn, Repositories(conn)

    def csrf(self, client=None, path="/contact"):
        client = client or self.client
        html = client.get(path).get_data(as_text=True)
        m = re.search(r'name="csrf-token" content="([^"]+)"', html)
        self.assertIsNotNone(m, "csrf meta tag missing")
        return m.group(1)

    def register(self, username="alice", email="alice@example.com", password=PASSWORD, client=None, **extra):
        client = client or self.client
        data = {"username": username, "email": email, "password": password, "accept_privacy": "1",
                "csrf_token": self.csrf(client), **extra}
        return client.post("/register", data=data)

    def login(self, identifier="alice", password=PASSWORD, client=None):
        client = client or self.client
        return client.post("/login", data={"identifier": identifier, "password": password,
                                           "csrf_token": self.csrf(client)})

    def reset_rate_limits(self):
        conn, _ = self.repos()
        conn.execute("DELETE FROM rate_limits")
        conn.close()

    def make_admin(self, username="admin", email="admin@example.com"):
        c = self.app.test_client()
        self.register(username, email, client=c)
        conn, r = self.repos()
        with transaction(conn):
            r.users.set_role(r.users.get_by_login(username)["id"], "admin")
        conn.close()
        self.login(username, client=c)
        return c

    def release_payload(self, **over):
        data = {"version": "1.0.0", "channel": "PUBLIC_BETA", "release_date": "2026-10-01",
                "download_url": "https://downloads.example.com/VRIOSCU-Setup-1.0.0.exe",
                "release_notes_url": "https://example.com/notes/1.0.0",
                "installer_filename": "VRIOSCU-Setup-1.0.0.exe", "sha256": SHA,
                "file_size_bytes": "52428800", "minimum_supported_version": "", "is_published": "1"}
        data.update(over)
        return data

    def api_headers(self, client):
        return {"X-CSRF-Token": client.get("/api/v1/me").get_json()["csrf_token"]}

    def session_cookie(self, client):
        name = self.app.config["SESSION_COOKIE_NAME_VR"]
        c = client.get_cookie(name)
        return c.value if c else None
