import os
import unittest

from app.config import ConfigError, load_settings
from tests.helpers import AppTestCase


class ProductionConfigTests(unittest.TestCase):
    def _load(self, **over):
        base = {"env": "production", "secret_key": "s" * 48, "base_url": "https://vrioscu.com",
                "database_path": "/tmp/vr-prod-test.db"}
        base.update(over)
        return load_settings(base)

    def test_valid_production_config_loads(self):
        s = self._load()
        self.assertTrue(s.is_production)
        self.assertTrue(s.https)

    def test_rejects_missing_or_weak_secret(self):
        for bad in ("short", "change-me"):
            with self.assertRaises(ConfigError):
                self._load(secret_key=bad)

    def test_rejects_http_base_url(self):
        with self.assertRaises(ConfigError):
            self._load(base_url="http://vrioscu.com")

    def test_rejects_database_inside_static(self):
        from app.config import BASE_DIR
        with self.assertRaises(ConfigError):
            self._load(database_path=str(BASE_DIR / "app" / "static" / "x.db"))

    def test_rejects_insecure_download_url(self):
        os.environ["DOWNLOAD_URL"] = "http://example.com/setup.exe"
        try:
            with self.assertRaises(ConfigError):
                self._load()
        finally:
            del os.environ["DOWNLOAD_URL"]

    def test_debug_never_enabled(self):
        from app import create_app
        app = create_app({"env": "production", "secret_key": "s" * 48, "base_url": "https://vrioscu.com",
                          "database_path": "/tmp/vr-prod-test2.db"})
        self.assertFalse(app.debug)
        self.assertFalse(app.config["DEBUG"])


class HeaderTests(AppTestCase):
    def test_security_headers_on_public_pages(self):
        r = self.client.get("/")
        h = r.headers
        self.assertIn("default-src 'self'", h["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", h["Content-Security-Policy"])
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertEqual(h["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertIn("camera=()", h["Permissions-Policy"])
        self.assertIn("X-Request-ID", h)
        self.assertNotIn("Strict-Transport-Security", h)  # http in tests

    def test_no_store_on_account_pages(self):
        self.register()
        r = self.client.get("/account")
        self.assertEqual(r.headers["Cache-Control"], "no-store")


class HttpsHeaderTests(AppTestCase):
    base_url = "https://vrioscu.test"

    def test_hsts_and_host_prefixed_secure_cookie(self):
        r = self.client.get("/", base_url="https://vrioscu.test")
        self.assertIn("max-age=", r.headers["Strict-Transport-Security"])
        self.assertIn("upgrade-insecure-requests", r.headers["Content-Security-Policy"])
        self.assertEqual(self.app.config["SESSION_COOKIE_NAME_VR"], "__Host-vr_session")
        html = r.get_data(as_text=True)
        import re
        token = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
        r = self.client.post("/register", base_url="https://vrioscu.test", data={
            "username": "secure", "email": "s@example.com", "password": "correct horse battery",
            "accept_privacy": "1", "csrf_token": token})
        cookie = [v for k, v in r.headers if k == "Set-Cookie" and v.startswith("__Host-vr_session")][0]
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Path=/", cookie)


class CsrfTests(AppTestCase):
    def test_post_without_token_rejected(self):
        r = self.client.post("/login", data={"identifier": "x", "password": "y"})
        self.assertEqual(r.status_code, 400)

    def test_post_with_wrong_token_rejected(self):
        self.client.get("/login")
        r = self.client.post("/login", data={"identifier": "x", "password": "y", "csrf_token": "forged"})
        self.assertEqual(r.status_code, 400)

    def test_cross_origin_post_rejected(self):
        token = self.csrf()
        r = self.client.post("/login", data={"identifier": "x", "password": "y", "csrf_token": token},
                             headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_api_unsafe_method_requires_header(self):
        self.register()
        r = self.client.put("/api/v1/me/preferences", json={"product_updates": True})
        self.assertEqual(r.status_code, 400)
        r = self.client.put("/api/v1/me/preferences", json={"product_updates": True},
                            headers=self.api_headers(self.client))
        self.assertEqual(r.status_code, 200)


class FileExposureTests(AppTestCase):
    def test_database_and_source_not_served(self):
        for path in ("/static/../instance/vrioscu.db", "/static/..%2F..%2Fwsgi.py", "/test.db", "/.env",
                     "/static/../../.env", "/migrations/0001_initial.sql"):
            r = self.client.get(path)
            self.assertIn(r.status_code, (404, 400), path)
            self.assertNotIn(b"CREATE TABLE", r.data)
            self.assertNotIn(b"SECRET_KEY", r.data)

    def test_database_file_permissions(self):
        mode = os.stat(self.db_path).st_mode & 0o777
        self.assertEqual(mode, 0o600)


class ErrorHandlingTests(AppTestCase):
    def test_api_404_is_structured_json(self):
        r = self.client.get("/api/v1/does-not-exist")
        self.assertEqual(r.status_code, 404)
        body = r.get_json()
        self.assertEqual(body["error"]["code"], "not_found")
        self.assertIn("request_id", body["error"])

    def test_unhandled_exception_hides_internals(self):
        @self.app.get("/__boom")
        def boom():
            raise RuntimeError("secret internal detail /home/app/db.sqlite")
        r = self.client.get("/__boom")
        self.assertEqual(r.status_code, 500)
        text = r.get_data(as_text=True)
        self.assertNotIn("secret internal detail", text)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("/home/app", text)

    def test_html_404_page(self):
        r = self.client.get("/missing-page")
        self.assertEqual(r.status_code, 404)
        self.assertIn("Page not found", r.get_data(as_text=True))

    def test_payload_too_large(self):
        token = self.csrf(path="/contact")
        r = self.client.post("/contact", data={"csrf_token": token, "message": "x" * 70000})
        self.assertEqual(r.status_code, 413)


class SeoTests(AppTestCase):
    def test_meta_tags(self):
        html = self.client.get("/features").get_data(as_text=True)
        self.assertIn("<title>Features | VRIOSCU</title>", html)
        self.assertIn('name="description"', html)
        self.assertIn('rel="canonical" href="http://localhost/features"', html)
        self.assertIn('property="og:title"', html)
        self.assertIn('name="twitter:card"', html)

    def test_robots_and_sitemap(self):
        robots = self.client.get("/robots.txt").get_data(as_text=True)
        self.assertIn("Disallow: /admin", robots)
        self.assertIn("Sitemap: http://localhost/sitemap.xml", robots)
        sm = self.client.get("/sitemap.xml")
        self.assertEqual(sm.mimetype, "application/xml")
        self.assertIn(b"<loc>http://localhost/download</loc>", sm.data)
        self.assertNotIn(b"/admin", sm.data)

    def test_private_pages_noindex(self):
        self.assertIn('content="noindex', self.client.get("/login").get_data(as_text=True))


class BrandingTests(AppTestCase):
    def test_no_forbidden_names_or_claims(self):
        forbidden = ["Vristu", "Artifact Validator", "Microsoft verified", "Windows certified", "SOC 2",
                     "ISO 27001", "GDPR compliant", "100% private", "Zero data collection"]
        for path in ("/", "/product", "/features", "/how-it-works", "/use-cases", "/public-beta", "/download",
                     "/documentation", "/privacy", "/contact"):
            html = self.client.get(path).get_data(as_text=True)
            for word in forbidden:
                self.assertNotIn(word, html, f"{word!r} found on {path}")

    def test_unsigned_beta_stated_honestly(self):
        html = self.client.get("/download").get_data(as_text=True)
        self.assertIn("Not signed yet", html)
        self.assertIn("Don't disable SmartScreen", html)
