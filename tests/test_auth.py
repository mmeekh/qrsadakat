from __future__ import annotations

import sqlite3
from contextlib import closing
from urllib.parse import parse_qs, urlencode, urlsplit

from cheabby import config, db
from cheabby.accounts import digest
from tests.harness import ServerTest


class GoogleSignInTest(ServerTest):
    def test_signed_out_scan_stamps_right_after_google(self):
        owner, customer = self.client(), self.client()
        merchant = self.open_business(owner, "owner")
        location, start = self.login(customer, "cust", intent="card", slug=merchant["slug"], scan=self.qr_token(owner))
        self.assertTrue(start["scan_ok"])
        self.assertEqual(location, f"/?c={merchant['slug']}&stamp=ok")
        card = self.call(customer, f"/api/card/{merchant['slug']}")["card"]
        self.assertEqual((card["stamps"], card["visits"]), (1, 1))
        me = self.call(customer, "/api/me")
        self.assertEqual((me["user"]["name"], me["merchant"], len(me["cards"])), ("Test Kişi", None, 1))
        recent = self.call(owner, "/api/dashboard")["recent"]
        self.assertEqual(recent[0]["customer"], "Test K.")

    def test_expired_qr_signs_in_without_stamp(self):
        owner, customer = self.client(), self.client()
        merchant = self.open_business(owner, "owner")
        location, start = self.login(customer, "cust", intent="card", slug=merchant["slug"], scan="1.abc")
        self.assertFalse(start["scan_ok"])
        self.assertEqual(location, f"/?c={merchant['slug']}")
        self.assertEqual(self.call(customer, f"/api/card/{merchant['slug']}")["card"]["stamps"], 0)

    def test_state_is_single_use_and_bound_to_the_browser(self):
        victim, attacker = self.client(), self.client()
        start = self.call(victim, "/api/auth/start", {"intent": "cards"})
        query = parse_qs(urlsplit(start["url"]).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["redirect_uri"], [self.base + "/auth/google/callback"])
        callback = "/auth/google/callback?" + urlencode({"code": "x", "state": query["state"][0]})
        # Another browser cannot finish this sign-in, and the attempt burns the state.
        self.assertEqual(self.open(attacker, callback).headers["Location"], "/?login=failed")
        self.assertEqual(self.open(victim, callback).headers["Location"], "/?login=failed")
        self.assertIsNone(self.call(attacker, "/api/me")["user"])

    def test_rejected_claims_do_not_sign_in(self):
        for claims in ({"email_verified": False}, {"aud": "someone-else"}, {"nonce": "wrong"},
                       {"iss": "https://evil.example"}):
            browser = self.client()
            location, _ = self.login(browser, "x", **claims)
            self.assertEqual(location, "/?view=cards&login=failed", claims)
            self.assertIsNone(self.call(browser, "/api/me")["user"])

    def test_cancelled_consent_and_missing_configuration(self):
        browser = self.client()
        start = self.call(browser, "/api/auth/start", {"intent": "map"})
        state = parse_qs(urlsplit(start["url"]).query)["state"][0]
        response = self.open(browser, "/auth/google/callback?" + urlencode({"error": "access_denied", "state": state}))
        self.assertEqual(response.headers["Location"], "/?view=map&login=cancelled")
        config.GOOGLE_CLIENT_SECRET = ""
        self.call(browser, "/api/auth/start", {"intent": "map"}, 503)
        self.assertFalse(self.call(browser, "/api/config")["google_enabled"])

    def test_first_pilot_accounts_carry_over(self):
        self.sql("""INSERT INTO merchants(name,email,password_hash,business_name,slug,reward_title,
          stamps_required,created_at) VALUES('Ayşe','ayse@example.com','x','Eski Kafe','eski','Kahve',5,'2026-09-26')""")
        self.sql("INSERT INTO customers(token_hash,created_at) VALUES(?,'2026-09-26')", (digest("old-cookie"),))
        self.sql("INSERT INTO cards(merchant_id,customer_id,stamps,visits,created_at) VALUES(1,1,3,3,'2026-09-26')")
        owner, customer = self.client(), self.client()
        self.login(owner, "ayse-google", email="Ayse@Example.com", intent="merchant")
        self.assertEqual(self.call(owner, "/api/me")["merchant"]["business_name"], "Eski Kafe")
        self.set_cookie(customer, "loyalty_customer", "old-cookie")
        self.login(customer, "old-customer")
        self.assertEqual(self.call(customer, "/api/card/eski")["card"]["stamps"], 3)

    def test_logout(self):
        browser = self.client()
        self.login(browser, "u")
        self.assertIsNotNone(self.call(browser, "/api/me")["user"])
        self.call(browser, "/api/logout", {})
        self.assertIsNone(self.call(browser, "/api/me")["user"])


class MigrationTest(ServerTest):
    def test_first_pilot_database_upgrades_in_place(self):
        path = config.DB_PATH.with_name("old.sqlite3")
        config.DB_PATH = path
        with sqlite3.connect(path) as old:
            old.executescript("""CREATE TABLE merchants (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, business_name TEXT NOT NULL,
              slug TEXT NOT NULL UNIQUE, reward_title TEXT NOT NULL, stamps_required INTEGER NOT NULL,
              created_at TEXT NOT NULL);
              INSERT INTO merchants VALUES(1,'A','a@example.com','h','Kafe','k','Kahve',5,'2026-09-26');""")
        db.migrate()
        db.migrate()
        with closing(db.connect()) as upgraded:
            self.assertEqual(upgraded.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRATIONS))
            row = upgraded.execute("SELECT business_name, user_id, lat, reward_type FROM merchants").fetchone()
            self.assertEqual(tuple(row), ("Kafe", None, None, "custom"))
