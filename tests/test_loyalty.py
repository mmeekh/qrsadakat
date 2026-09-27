from __future__ import annotations

from cheabby import loyalty
from tests.harness import ServerTest


class StampCardTest(ServerTest):
    def test_rotating_qr_stamp_reward_and_business_isolation(self):
        owner, other, customer = self.client(), self.client(), self.client()
        merchant = self.open_business(owner, "owner")
        self.open_business(other, "other", "Diğer Kafe")
        slug = merchant["slug"]
        self.login(customer, "cust")
        token, other_token = self.qr_token(owner), self.qr_token(other)
        self.call(customer, f"/api/card/{slug}/scan", {"scan_token": other_token}, 400)
        self.call(customer, f"/api/card/{slug}/scan", {"scan_token": "invalid"}, 400)
        stale = loyalty.make_scan_token(merchant["id"], int(token.split(".")[0]) - 2)
        self.call(customer, f"/api/card/{slug}/scan", {"scan_token": stale}, 400)
        self.assertFalse(self.call(customer, f"/api/card/{slug}/scan", {"scan_token": token})["earned_reward"])
        self.call(customer, f"/api/card/{slug}/scan", {"scan_token": token}, 429)

        self.age_stamps()
        self.assertTrue(self.call(customer, f"/api/card/{slug}/scan", {"scan_token": token})["earned_reward"])
        card = self.call(customer, f"/api/card/{slug}")["card"]
        self.assertEqual((card["visits"], card["stamps"], card["rewards_available"]), (2, 0, 1))

        self.call(customer, f"/api/card/{slug}/redeem", {})
        self.call(customer, f"/api/card/{slug}/redeem", {}, 409)
        reward_id = self.call(owner, "/api/dashboard")["redemptions"][0]["id"]
        self.call(other, f"/api/redemptions/{reward_id}/approve", {}, 404)
        self.call(owner, f"/api/redemptions/{reward_id}/approve", {})
        card = self.call(customer, f"/api/card/{slug}")["card"]
        self.assertEqual((card["rewards_available"], card["rewards_redeemed"]), (0, 1))
        metrics = self.call(owner, "/api/dashboard")["metrics"]
        self.assertEqual((metrics["customers"], metrics["returning"], metrics["visits"]), (1, 1, 2))

    def test_non_owners_are_refused(self):
        owner, stranger = self.client(), self.client()
        self.open_business(owner, "owner")
        self.assertIsNone(self.call(stranger, "/api/card/" + self.call(owner, "/api/me")["merchant"]["slug"])["card"])
        self.call(stranger, "/api/merchant/qr", expected=401)
        self.login(stranger, "customer")
        self.call(stranger, "/api/merchant/qr", expected=403)
        self.call(stranger, "/api/dashboard", expected=403)
        self.call(stranger, "/api/card/unknown", expected=404)


class GuestStampTest(ServerTest):
    def test_first_stamp_without_sign_in_then_saved_to_google(self):
        owner, other, guest = self.client(), self.client(), self.client()
        slug = self.open_business(owner, "owner")["slug"]
        other_slug = self.open_business(other, "other", "Diğer Kafe")["slug"]
        first = self.call(guest, f"/api/card/{slug}/scan", {"scan_token": self.qr_token(owner)})
        self.assertEqual((first["guest"], first["earned_reward"]), (True, False))
        self.assertEqual(self.call(guest, f"/api/card/{slug}")["card"]["stamps"], 1)
        self.assertEqual(len(self.call(guest, "/api/me")["cards"]), 1)
        self.assertEqual(self.call(guest, "/api/places")["places"][1]["mine"]["stamps"], 1)
        self.assertEqual(self.call(owner, "/api/dashboard")["recent"][0]["customer"], "Misafir")
        self.call(guest, f"/api/card/{slug}/scan", {"scan_token": self.qr_token(owner)}, 429)
        # One business only while signed out; rewards always need the account.
        self.call(guest, f"/api/card/{other_slug}/scan", {"scan_token": self.qr_token(other)}, 401)
        self.call(guest, f"/api/card/{slug}/redeem", {}, 401)

        self.login(guest, "cust")
        me = self.call(guest, "/api/me")
        self.assertEqual((me["user"]["name"], [c["stamps"] for c in me["cards"]]), ("Test Kişi", [1]))
        self.call(guest, f"/api/card/{other_slug}/scan", {"scan_token": self.qr_token(other)})
        self.assertEqual(self.call(owner, "/api/dashboard")["recent"][0]["customer"], "Test K.")

    def test_guest_stamps_never_add_to_an_existing_card(self):
        owner, phone = self.client(), self.client()
        slug = self.open_business(owner, "owner")["slug"]
        self.login(phone, "cust")
        self.call(phone, f"/api/card/{slug}/scan", {"scan_token": self.qr_token(owner)})
        private_window = self.client()
        self.call(private_window, f"/api/card/{slug}/scan", {"scan_token": self.qr_token(owner)})
        self.login(private_window, "cust")
        self.assertEqual(self.call(private_window, f"/api/card/{slug}")["card"]["stamps"], 1)

    def test_a_forged_guest_cookie_is_just_a_new_guest(self):
        owner, guest = self.client(), self.client()
        slug = self.open_business(owner, "owner")["slug"]
        self.set_cookie(guest, "loyalty_customer", "made-up")
        self.assertIsNone(self.call(guest, f"/api/card/{slug}")["card"])
        self.call(guest, f"/api/card/{slug}/scan", {"scan_token": self.qr_token(owner)})
        self.assertEqual(self.call(guest, f"/api/card/{slug}")["card"]["stamps"], 1)


class ProfileAndMapTest(ServerTest):
    def test_profile_rules_and_fixed_stamp_goal(self):
        owner = self.client()
        self.login(owner, "owner", intent="merchant")
        base = {"business_name": "Kafe", "reward_title": "Kahve", "stamps_required": 5,
                "category": "Kafe", "address": "Moda", "lat": 40.9, "lng": 29.0}
        for broken in ({"lat": None}, {"lat": 0, "lng": 0}, {"lat": 91}, {"category": "Uzay"},
                       {"stamps_required": 1}, {"business_name": "  "}):
            self.call(owner, "/api/merchant", {**base, **broken}, 400)
        created = self.call(owner, "/api/merchant", base)["merchant"]
        updated = self.call(owner, "/api/merchant", {**base, "business_name": "Yeni Ad", "stamps_required": 9})["merchant"]
        self.assertEqual((updated["slug"], updated["business_name"], updated["stamps_required"]),
                         (created["slug"], "Yeni Ad", 5))

    def test_map_lists_pinned_places_with_my_progress(self):
        owner, customer, guest = self.client(), self.client(), self.client()
        merchant = self.open_business(owner, "owner")
        self.sql("""INSERT INTO merchants(name,email,password_hash,business_name,slug,reward_title,stamps_required,
          created_at) VALUES('x','nopin@example.com','','Pinsiz','pinsiz','Kahve',5,'2026-09-26')""")
        self.login(customer, "cust", intent="card", slug=merchant["slug"], scan=self.qr_token(owner))
        places = self.call(guest, "/api/places")["places"]
        self.assertEqual([p["business_name"] for p in places], ["Nora Café"])
        self.assertIsNone(places[0]["mine"])
        mine = self.call(customer, "/api/places")["places"][0]["mine"]
        self.assertEqual(mine, {"stamps": 1, "rewards_available": 0})
        self.call(guest, "/api/geocode?q=Moda", expected=401)
        self.call(customer, "/api/geocode?q=a", expected=400)

    def test_demo_is_seeded_once_and_only_shown_in_demo_mode(self):
        from cheabby import config, demo
        self.call(self.client(), "/api/demo/login", {}, 404)
        demo.seed_demo()
        demo.seed_demo()
        self.assertEqual(self.call(self.client(), "/api/places")["places"], [])
        config.DEMO_MODE = True
        browser = self.client()
        self.assertTrue(self.call(browser, "/api/config")["demo_enabled"])
        self.call(browser, "/api/demo/login", {})
        metrics = self.call(browser, "/api/dashboard")["metrics"]
        self.assertEqual((metrics["customers"], metrics["returning"], metrics["visits"]), (3, 2, 10))
        self.assertEqual(len(self.call(browser, "/api/places")["places"]), len(demo.DEMO_PLACES))

    def test_static_files_and_security_headers(self):
        browser = self.client()
        for path in ("/", "/js/main.js", "/styles.css", "/vendor/qrcode.min.js", "/vendor/leaflet/leaflet.js",
                     "/cafe-card-bg.webp"):
            response = self.open(browser, path)
            self.assertEqual(response.status, 200, path)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertGreater(len(response.read()), 100, path)
        self.assertEqual(self.open(browser, "/../cheabby/config.py").status, 404)
        self.assertEqual(self.open(browser, "/api/me").headers["Cache-Control"], "no-store")
