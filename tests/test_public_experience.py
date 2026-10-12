"""Public release boundaries and report navigation regressions."""
from dataclasses import replace
from html.parser import HTMLParser

from tests.helpers import AppTestCase


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for attr in ("src", "href"):
            value = attrs.get(attr, "")
            if value.startswith("/static/"):
                self.assets.add(value)


class PublicExperienceTests(AppTestCase):
    def test_published_release_is_automatically_available(self):
        admin = self.make_admin()
        response = admin.post("/api/v1/admin/releases", json=self.release_payload(), headers=self.api_headers(admin))
        self.assertEqual(response.status_code,201)
        rid = response.get_json()["release"]["id"]
        self.assertIn("Download installer",self.client.get("/download").get_data(as_text=True))
        self.assertEqual(self.client.get(f"/download/{rid}").status_code,302)
        self.assertEqual(self.client.get("/api/v1/releases/latest").status_code,200)

    def test_coming_soon_blocks_config_fallback(self):
        settings = self.app.config["SETTINGS"]
        settings.product = replace(settings.product, download_url="https://downloads.example.com/setup.exe")
        self.assertEqual(self.client.get("/download/latest").status_code, 404)
        self.assertNotIn("Download installer", self.client.get("/download").get_data(as_text=True))

    def test_public_pages_and_referenced_assets_load(self):
        assets = set()
        for path in ("/", "/product", "/features", "/how-it-works", "/reports", "/documentation",
                     "/use-cases", "/public-beta", "/download", "/contact", "/privacy", "/login", "/register"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            parser = AssetParser()
            parser.feed(response.get_data(as_text=True))
            assets.update(parser.assets)
        for path in assets:
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200, path)

    def test_historical_report_and_ai_output_are_explicit(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("No live endpoint checks", html)
        self.assertIn("AI Validation Insights", html)
        self.assertIn("High (Deterministic Analysis)", html)
        self.assertIn("23-page", html)
        self.assertIn("Historical sample results", html)
        self.assertIn(b"<loc>http://localhost/reports</loc>",self.client.get("/sitemap.xml").data)
