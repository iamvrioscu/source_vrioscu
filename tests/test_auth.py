import html

from app.db import transaction
from app.services.auth import token_hash
from tests.helpers import PASSWORD, AppTestCase


class RegistrationTests(AppTestCase):
    def test_register_creates_hashed_account_and_signs_in(self):
        r = self.register(first_name="Alice", country="India", purpose="site_integration")
        self.assertEqual(r.status_code, 303)
        self.assertIn("/account", r.headers["Location"])
        conn, repos = self.repos()
        u = repos.users.get_by_login("alice")
        self.assertTrue(u["password_hash"].startswith("scrypt:"))
        self.assertNotIn(PASSWORD, u["password_hash"])
        self.assertEqual(u["role"], "user")
        consents = repos.preferences.consent_history(u["id"])
        self.assertEqual({c["purpose"] for c in consents}, {"privacy_notice", "product_updates"})
        self.assertFalse(repos.preferences.get_updates(u["id"]), "updates must default to off")
        conn.close()
        self.assertEqual(self.client.get("/account").status_code, 200)

    def test_product_updates_opt_in_is_separate(self):
        self.register(product_updates="1")
        conn, repos = self.repos()
        self.assertTrue(repos.preferences.get_updates(repos.users.get_by_login("alice")["id"]))
        conn.close()

    def test_privacy_acknowledgement_required(self):
        token = self.csrf(path="/register")
        r = self.client.post("/register", data={"username": "bob", "email": "b@example.com",
                                                "password": PASSWORD, "csrf_token": token})
        self.assertEqual(r.status_code, 422)
        self.assertIn("privacy notice", r.get_data(as_text=True))

    def test_duplicate_username_and_email(self):
        self.register()
        c2 = self.app.test_client()
        r = self.register("ALICE", "other@example.com", client=c2)
        self.assertEqual(r.status_code, 422)
        self.assertIn("username is taken", r.get_data(as_text=True))
        r = self.register("carol", "Alice@Example.com", client=c2)
        self.assertEqual(r.status_code, 422)
        self.assertIn("already exists", r.get_data(as_text=True))

    def test_password_rules(self):
        for pw, msg in [("short", "at least 12"), ("password1234", "less common"),
                        ("alice-forever-123", "can't contain")]:
            c = self.app.test_client()
            r = self.register(password=pw, client=c)
            self.assertEqual(r.status_code, 422, pw)
            self.assertIn(msg, html.unescape(r.get_data(as_text=True)))

    def test_invalid_inputs(self):
        cases = [{"username": "a"}, {"username": "bad name!"}, {"email": "not-an-email"},
                 {"country": "Atlantis"}, {"purpose": "hacking"}, {"first_name": "<script>"}]
        for case in cases:
            self.reset_rate_limits()
            c = self.app.test_client()
            data = {"username": "dave", "email": "d@example.com", **case}
            r = self.register(client=c, **data)
            self.assertEqual(r.status_code, 422, case)

    def test_password_not_echoed_back(self):
        r = self.register(password="short-pw")
        self.assertNotIn("short-pw", r.get_data(as_text=True))


class LoginTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register(client=self.app.test_client())

    def test_login_with_username_or_email(self):
        for ident in ("alice", "ALICE@example.com"):
            c = self.app.test_client()
            r = self.login(ident, client=c)
            self.assertEqual(r.status_code, 303, ident)
            cookie = [v for k, v in r.headers if k == "Set-Cookie" and v.startswith("vr_session")][0]
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Lax", cookie)

    def test_wrong_password_and_unknown_user_same_message(self):
        a = self.login("alice", "wrong password!!").get_data(as_text=True)
        b = self.login("nobody", "wrong password!!").get_data(as_text=True)
        msg = "Email/username or password is incorrect."
        self.assertIn(msg, a)
        self.assertIn(msg, b)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.login("alice", "wrong password!!")
        r = self.login("alice", PASSWORD)
        self.assertEqual(r.status_code, 401)
        self.assertIn("Too many failed attempts", r.get_data(as_text=True))

    def test_disabled_account_cannot_sign_in(self):
        conn, repos = self.repos()
        with transaction(conn):
            repos.users.set_active(repos.users.get_by_login("alice")["id"], False)
        conn.close()
        self.assertEqual(self.login().status_code, 401)

    def test_open_redirect_blocked(self):
        for target in ("//evil.example/x", "https://evil.example", "/\\evil.example", "javascript:alert(1)"):
            c = self.app.test_client()
            token = self.csrf(c)
            r = c.post(f"/login?next={target}", data={"identifier": "alice", "password": PASSWORD,
                                                      "csrf_token": token})
            self.assertEqual(r.status_code, 303)
            self.assertTrue(r.headers["Location"].startswith("/"), target)
            self.assertNotIn("evil", r.headers["Location"])

    def test_safe_next_honoured(self):
        token = self.csrf()
        r = self.client.post("/login?next=/account/feedback", data={"identifier": "alice", "password": PASSWORD,
                                                                    "csrf_token": token})
        self.assertEqual(r.headers["Location"], "/account/feedback")


class SessionTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register()

    def test_logout_revokes_server_session(self):
        raw = self.session_cookie(self.client)
        token = self.csrf(path="/account")
        self.assertEqual(self.client.post("/logout", data={"csrf_token": token}).status_code, 303)
        # Replaying the old cookie must not work.
        c = self.app.test_client()
        c.set_cookie(self.app.config["SESSION_COOKIE_NAME_VR"], raw)
        self.assertEqual(c.get("/account").status_code, 302)

    def test_logout_requires_post(self):
        self.assertEqual(self.client.get("/logout").status_code, 405)

    def test_session_token_stored_hashed(self):
        raw = self.session_cookie(self.client)
        conn, _ = self.repos()
        hashes = [r[0] for r in conn.execute("SELECT token_hash FROM sessions")]
        conn.close()
        self.assertIn(token_hash(raw), hashes)
        self.assertNotIn(raw, hashes)

    def test_idle_timeout(self):
        conn, _ = self.repos()
        conn.execute("UPDATE sessions SET last_seen_at = '2000-01-01T00:00:00Z'")
        conn.close()
        self.assertEqual(self.client.get("/account").status_code, 302)

    def test_absolute_expiry(self):
        conn, _ = self.repos()
        conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00Z'")
        conn.close()
        self.assertEqual(self.client.get("/account").status_code, 302)

    def test_login_rotates_session(self):
        before = self.session_cookie(self.client)
        self.login()
        after = self.session_cookie(self.client)
        self.assertNotEqual(before, after)
        c = self.app.test_client()
        c.set_cookie(self.app.config["SESSION_COOKIE_NAME_VR"], before)
        self.assertEqual(c.get("/account").status_code, 302)
