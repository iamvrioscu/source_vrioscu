from tests.helpers import SHA, AppTestCase


class ReleaseManagementTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.h = self.api_headers(self.admin)

    def create(self, **over):
        return self.admin.post("/api/v1/admin/releases", json=self.release_payload(**over), headers=self.h)

    def test_create_and_publish_release(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.get_json())
        rel = r.get_json()["release"]
        self.assertTrue(rel["is_published"])
        html = self.client.get("/download").get_data(as_text=True)
        self.assertIn(SHA, html)
        self.assertIn("VRIOSCU-Setup-1.0.0.exe", html)
        self.assertIn("50.0 MB", html)

    def test_html_form_create(self):
        token = self.csrf(self.admin, "/admin/releases/new")
        r = self.admin.post("/admin/releases/new", data={**self.release_payload(version="1.0.1"), "csrf_token": token})
        self.assertEqual(r.status_code, 303)

    def test_rejects_unsafe_download_urls(self):
        for url in ("http://downloads.example.com/a.exe", "file:///C:/Users/dev/setup.exe",
                    "https://localhost/a.exe", "https://127.0.0.1/a.exe", "https://192.168.1.10/a.exe",
                    "https://10.0.0.5/a.exe", "https://user:pw@example.com/a.exe", "javascript:alert(1)",
                    "\\\\devbox\\share\\setup.exe"):
            r = self.create(download_url=url)
            self.assertEqual(r.status_code, 422, url)
            self.assertIn("download_url", r.get_json()["error"]["fields"])

    def test_field_validation(self):
        bad = [{"version": "v1"}, {"channel": "NIGHTLY"}, {"sha256": "abc"}, {"sha256": "g" * 64},
               {"installer_filename": "../evil.exe"}, {"installer_filename": "setup.bat"},
               {"file_size_bytes": "0"}, {"release_date": "2026-13-40"},
               {"minimum_supported_version": "2.0.0"}]
        for case in bad:
            r = self.create(**case)
            self.assertEqual(r.status_code, 422, case)

    def test_duplicate_version_channel(self):
        self.create()
        r = self.create()
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.create(channel="STABLE").status_code, 201)

    def test_public_api_and_update_check(self):
        self.create(version="1.0.0", release_date="2026-10-01")
        self.create(version="1.1.0", release_date="2026-11-01", minimum_supported_version="1.0.5")
        r = self.client.get("/api/v1/releases/latest?channel=PUBLIC_BETA&current_version=1.0.0")
        body = r.get_json()["release"]
        self.assertEqual(body["version"], "1.1.0")
        self.assertTrue(body["update_available"])
        self.assertTrue(body["update_required"])
        self.assertNotIn("download_url", body, "public API returns the tracked download path, not raw URL")
        self.assertTrue(body["download_path"].startswith("/download/"))
        r = self.client.get("/api/v1/releases/latest?current_version=1.1.0").get_json()["release"]
        self.assertFalse(r["update_available"])
        self.assertEqual(self.client.get("/api/v1/releases/latest?current_version=junk").status_code, 400)

    def test_internal_and_dev_channels_not_public(self):
        rid = self.create(channel="INTERNAL").get_json()["release"]["id"]
        self.create(channel="DEV", version="9.9.9")
        self.assertEqual(self.client.get("/api/v1/releases/latest?channel=INTERNAL").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/releases").get_json()["releases"], [])
        self.assertEqual(self.client.get(f"/download/{rid}").status_code, 404)
        self.assertNotIn("9.9.9", self.client.get("/download").get_data(as_text=True))

    def test_unpublished_release_hidden(self):
        rid = self.create(is_published="").get_json()["release"]["id"]
        self.assertEqual(self.client.get(f"/download/{rid}").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/releases/latest").status_code, 404)

    def test_download_redirect_counts_without_identifiers(self):
        rid = self.create().get_json()["release"]["id"]
        for _ in range(3):
            r = self.client.get(f"/download/{rid}")
            self.assertEqual(r.status_code, 302)
            self.assertEqual(r.headers["Location"], "https://downloads.example.com/VRIOSCU-Setup-1.0.0.exe")
        self.assertEqual(self.client.get("/download/latest").status_code, 302)
        conn, repos = self.repos()
        self.assertEqual(repos.releases.download_totals()[rid], 4)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(download_stats)")]
        conn.close()
        self.assertEqual(cols, ["release_id", "day", "count"])

    def test_patch_and_delete(self):
        rid = self.create().get_json()["release"]["id"]
        r = self.admin.patch(f"/api/v1/admin/releases/{rid}", json={"is_mandatory": True}, headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["release"]["is_mandatory"])
        self.assertEqual(self.admin.delete(f"/api/v1/admin/releases/{rid}", headers=self.h).status_code, 204)
        self.assertEqual(self.admin.delete(f"/api/v1/admin/releases/{rid}", headers=self.h).status_code, 404)

    def test_release_changes_audited(self):
        self.create()
        conn, repos = self.repos()
        self.assertIn("release.created", [a["action"] for a in repos.audit.recent()])
        conn.close()

    def test_no_release_shows_honest_empty_state(self):
        html = self.client.get("/download").get_data(as_text=True)
        self.assertIn("hasn't been published yet", html)
        self.assertEqual(self.client.get("/download/latest").status_code, 404)

    def test_json_body_must_be_object(self):
        r = self.admin.post("/api/v1/admin/releases", json=[1, 2], headers=self.h)
        self.assertEqual(r.status_code, 400)
        r = self.admin.post("/api/v1/admin/releases", data="x", headers=self.h)
        self.assertEqual(r.status_code, 415)
