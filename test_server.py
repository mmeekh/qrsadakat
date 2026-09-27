"""Real HTTP flow for the merchant approval and reward boundary."""

import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import server as app


class PilotFlowTest(unittest.TestCase):
    def setUp(self):
        self.previous_demo_mode = app.DEMO_MODE
        app.DEMO_MODE = False
        self.temp = tempfile.TemporaryDirectory()
        app.DB_PATH = Path(self.temp.name) / "pilot.sqlite3"
        app.init_db()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.owner = self.client()
        self.customer = self.client()
        self.other = self.client()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()
        app.DEMO_MODE = self.previous_demo_mode

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, client, path, data=None, expected=200):
        headers = {"Content-Type": "application/json"}
        request = urllib.request.Request(self.base + path,
            data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            response = client.open(request)
        except urllib.error.HTTPError as error:
            response = error
        body = response.read().decode()
        self.assertEqual(response.status, expected, body)
        return json.loads(body)

    def register(self, client, email, name):
        return self.call(client, "/api/register", {"name": name, "business_name": name,
            "email": email, "password": "long-password-123", "reward_title": "2 ziyaret, 1 kahve",
            "stamps_required": 2})["merchant"]

    def test_rotating_qr_auto_stamp_reward_and_merchant_isolation(self):
        owner = self.register(self.owner, "owner@example.com", "Nora Café")
        other = self.register(self.other, "other@example.com", "Diğer Kafe")
        slug = owner["slug"]
        card = self.call(self.customer, f"/api/card/{slug}")
        self.assertEqual(card["card"]["stamps"], 0)
        self.call(self.customer, "/api/merchant/qr", expected=401)
        token = self.call(self.owner, "/api/merchant/qr")["scan_token"]
        other_token = self.call(self.other, "/api/merchant/qr")["scan_token"]
        self.call(self.customer, f"/api/card/{slug}/scan", {"scan_token": other_token}, 400)
        self.call(self.customer, f"/api/card/{slug}/scan", {"scan_token": "invalid"}, 400)
        old_slot = int(token.split(".")[0]) - 2
        self.call(self.customer, f"/api/card/{slug}/scan",
                  {"scan_token": app.make_scan_token(owner["id"], old_slot)}, 400)
        first = self.call(self.customer, f"/api/card/{slug}/scan", {"scan_token": token})
        self.assertTrue(first["awarded"])
        self.assertFalse(first["earned_reward"])
        self.call(self.customer, f"/api/card/{slug}/scan", {"scan_token": token}, 429)
        self.call(self.customer, f"/api/card/{slug}/visit", {}, 404)
        visit_id = self.call(self.owner, "/api/dashboard")["recent"][0]["id"]
        self.call(self.owner, f"/api/visits/{visit_id}/approve", {}, 404)

        with app.connect() as db:
            old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
            db.execute("UPDATE visits SET approved_at=? WHERE id=?", (old, visit_id))
        second = self.call(self.customer, f"/api/card/{slug}/scan", {"scan_token": token})
        self.assertTrue(second["earned_reward"])
        card = self.call(self.customer, f"/api/card/{slug}")["card"]
        self.assertEqual((card["visits"], card["stamps"], card["rewards_available"]), (2, 0, 1))

        self.call(self.customer, f"/api/card/{slug}/redeem", {}, 200)
        reward_id = self.call(self.owner, "/api/dashboard")["redemptions"][0]["id"]
        self.call(self.other, f"/api/redemptions/{reward_id}/approve", {}, 404)
        self.call(self.owner, f"/api/redemptions/{reward_id}/approve", {}, 200)
        self.call(self.customer, f"/api/card/{slug}/redeem", {}, 409)
        card = self.call(self.customer, f"/api/card/{slug}")["card"]
        self.assertEqual((card["rewards_available"], card["rewards_redeemed"]), (0, 1))
        metrics = self.call(self.owner, "/api/dashboard")["metrics"]
        self.assertEqual((metrics["customers"], metrics["returning"], metrics["visits"]), (1, 1, 2))

    def test_auth_and_frontend_assets(self):
        for path in ("/", "/app.js", "/styles.css", "/qrcode.min.js", "/cafe-card-bg.webp", "/shop-card-bg.webp"):
            with self.owner.open(self.base + path) as response:
                self.assertEqual(response.status, 200)
                if path.endswith(".webp"):
                    self.assertEqual(response.headers.get_content_type(), "image/webp")
                self.assertGreater(len(response.read()), 100)
        self.call(self.owner, "/api/register", {"name": "X", "business_name": "X",
            "email": "x@example.com", "password": "short", "reward_title": "Kahve", "stamps_required": 5}, 400)
        self.register(self.owner, "x@example.com", "Nora Café")
        self.call(self.owner, "/api/logout", {}, 200)
        self.call(self.owner, "/api/me", expected=401)
        self.call(self.owner, "/api/login", {"email": "x@example.com", "password": "wrong-password"}, 401)
        self.call(self.owner, "/api/login", {"email": "x@example.com", "password": "long-password-123"}, 200)
        self.assertEqual(self.call(self.owner, "/api/me")["merchant"]["business_name"], "Nora Café")

    def test_one_click_demo_is_seeded_once_and_config_gated(self):
        self.assertFalse(self.call(self.owner, "/api/config")["demo_enabled"])
        self.call(self.owner, "/api/demo/login", {}, 404)
        app.DEMO_MODE = True
        app.seed_demo()
        app.seed_demo()
        self.assertTrue(self.call(self.owner, "/api/config")["demo_enabled"])
        merchant = self.call(self.owner, "/api/demo/login", {})["merchant"]
        self.assertEqual(merchant["business_name"], "Nora Café")
        metrics = self.call(self.owner, "/api/dashboard")["metrics"]
        self.assertEqual((metrics["customers"], metrics["returning"], metrics["visits"]), (3, 2, 10))


if __name__ == "__main__":
    unittest.main()
