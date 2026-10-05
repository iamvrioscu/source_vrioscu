import sqlite3

from app.db import migrate, transaction
from tests.helpers import AppTestCase


class RateLimitTests(AppTestCase):
    def test_login_rate_limited(self):
        statuses = []
        token = self.csrf()
        for _ in range(22):
            r = self.client.post("/login", data={"identifier": f"u{_}", "password": "wrong password",
                                                 "csrf_token": token})
            statuses.append(r.status_code)
        self.assertIn(429, statuses)
        self.assertEqual(statuses[:20].count(429), 0)
        last = self.client.post("/login", data={"identifier": "x", "password": "y", "csrf_token": token})
        self.assertEqual(last.status_code, 429)
        self.assertTrue(int(last.headers["Retry-After"]) > 0)

    def test_contact_rate_limited(self):
        token = self.csrf(path="/contact")
        codes = [self.client.post("/contact", data={"csrf_token": token, "name": "A", "email": "a@example.com",
                                                    "topic": "general", "message": "hello there team"}).status_code
                 for _ in range(7)]
        self.assertEqual(codes[:5], [303] * 5)
        self.assertEqual(codes[5], 429)

    def test_rate_limit_keys_are_not_raw_ips(self):
        token = self.csrf()
        self.client.post("/login", data={"identifier": "x", "password": "y", "csrf_token": token},
                         environ_base={"REMOTE_ADDR": "203.0.113.7"})
        conn, _ = self.repos()
        buckets = [r[0] for r in conn.execute("SELECT bucket FROM rate_limits")]
        conn.close()
        self.assertTrue(buckets)
        self.assertFalse(any("203.0.113.7" in b for b in buckets))


class DatabaseTests(AppTestCase):
    def test_migrations_idempotent(self):
        self.assertEqual(migrate(self.app.config["SETTINGS"].database_path), [])

    def test_foreign_keys_and_wal(self):
        conn, _ = self.repos()
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        conn.close()

    def test_transaction_rolls_back(self):
        conn, repos = self.repos()
        with self.assertRaises(RuntimeError):
            with transaction(conn):
                repos.users.create(username="ghost", email="g@example.com", password_hash="x")
                raise RuntimeError("abort")
        self.assertIsNone(repos.users.get_by_login("ghost"))
        conn.close()

    def test_nested_transaction_savepoint(self):
        conn, repos = self.repos()
        with transaction(conn):
            repos.users.create(username="outer", email="o@example.com", password_hash="x")
            try:
                with transaction(conn):
                    repos.users.create(username="inner", email="i@example.com", password_hash="x")
                    raise ValueError
            except ValueError:
                pass
        self.assertIsNotNone(repos.users.get_by_login("outer"))
        self.assertIsNone(repos.users.get_by_login("inner"))
        conn.close()

    def test_schema_constraints(self):
        conn, repos = self.repos()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO users (username, email, password_hash, role, created_at, updated_at,"
                         " password_changed_at) VALUES ('x','x@x.io','h','superuser','t','t','t')")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO releases (version, channel, release_date, download_url, installer_filename,"
                         " sha256, file_size_bytes, created_at, updated_at) VALUES"
                         " ('1.0.0','PUBLIC_BETA','2026-01-01','https://x','a.exe','short',1,'t','t')")
        conn.close()

    def test_health_endpoint(self):
        self.assertEqual(self.client.get("/api/v1/health").get_json(), {"status": "ok"})


class PublicPagesTests(AppTestCase):
    def test_every_public_page_renders(self):
        for p in ("/", "/product", "/features", "/how-it-works", "/use-cases", "/public-beta", "/download",
                  "/documentation", "/privacy", "/contact", "/login", "/register"):
            r = self.client.get(p)
            self.assertEqual(r.status_code, 200, p)
            html = r.get_data(as_text=True)
            self.assertIn('<html lang="en"', html)
            self.assertIn('<main id="main"', html)
            self.assertIn('class="skip-link"', html)

    def test_no_inline_scripts_or_styles(self):
        import re
        for p in ("/", "/download", "/register", "/how-it-works"):
            html = self.client.get(p).get_data(as_text=True)
            self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), p)
            self.assertNotIn(" style=", html, p)
            self.assertNotIn("onclick=", html, p)

    def test_home_content(self):
        html = self.client.get("/").get_data(as_text=True)
        for text in ("Endpoint Validation &amp; Evidence Capture", "Validate.", "Capture.", "Document.",
                     "Download VRIOSCU", "Login"):
            self.assertIn(text, html)
