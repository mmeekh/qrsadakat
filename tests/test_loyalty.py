from __future__ import annotations

import urllib.error
import urllib.request

from bikiyak import config, demo, loyalty
from tests.harness import ServerTest


class StampCardTest(ServerTest):
    def test_rotating_qr_stamp_reward_and_business_isolation(self):
        owner, other, customer = self.client(), self.client(), self.client()
        card_id = self.open_business(owner, "owner")["id"]
        other_id = self.open_business(other, "other", "Diğer Kafe")["id"]
        self.login(customer, "cust")
        token, other_token = self.qr_token(owner, card_id), self.qr_token(other, other_id)
        scan = f"/api/card/{card_id}/scan"
        self.call(customer, scan, {"scan_token": other_token}, 400)
        self.call(customer, scan, {"scan_token": "invalid"}, 400)
        stale = loyalty.make_scan_token(card_id, int(token.split(".")[0]) - 2)
        self.call(customer, scan, {"scan_token": stale}, 400)
        self.assertFalse(self.call(customer, scan, {"scan_token": token})["earned_reward"])
        self.call(customer, scan, {"scan_token": token}, 429)

        self.age_stamps()
        self.assertTrue(self.call(customer, scan, {"scan_token": token})["earned_reward"])
        card = self.call(customer, f"/api/card/{card_id}")["card"]
        self.assertEqual((card["visits"], card["stamps"], card["rewards_available"]), (2, 0, 1))

        self.call(customer, f"/api/card/{card_id}/redeem", {})
        self.call(customer, f"/api/card/{card_id}/redeem", {}, 409)
        redemption = self.call(owner, "/api/dashboard")["redemptions"][0]
        self.assertEqual(redemption["program"], "2 damga topla, 1 kahve bedava")
        self.call(other, f"/api/redemptions/{redemption['id']}/approve", {}, 404)
        self.call(owner, f"/api/redemptions/{redemption['id']}/approve", {})
        card = self.call(customer, f"/api/card/{card_id}")["card"]
        self.assertEqual((card["rewards_available"], card["rewards_redeemed"]), (0, 1))
        metrics = self.call(owner, "/api/dashboard")["metrics"]
        self.assertEqual((metrics["customers"], metrics["returning"], metrics["visits"]), (1, 1, 2))

    def test_non_owners_are_refused(self):
        owner, stranger = self.client(), self.client()
        card_id = self.open_business(owner, "owner")["id"]
        self.assertIsNone(self.call(stranger, f"/api/card/{card_id}")["card"])
        self.call(stranger, f"/api/programs/{card_id}/qr", expected=401)
        self.login(stranger, "customer")
        self.call(stranger, f"/api/programs/{card_id}/qr", expected=403)
        self.call(stranger, "/api/programs", expected=403)
        self.call(stranger, "/api/dashboard", expected=403)
        self.call(stranger, "/api/card/999", expected=404)
        self.open_business(stranger, "stranger", "Başka")
        self.call(stranger, f"/api/programs/{card_id}/qr", expected=404)
        self.call(stranger, f"/api/programs/{card_id}/archive", {}, 404)


class RewardCardsTest(ServerTest):
    def test_one_business_runs_several_cards_up_to_five(self):
        owner, customer = self.client(), self.client()
        coffee = self.open_business(owner, "owner", required=3)
        dessert = self.new_card(owner, 8, reward_type="percent", reward_amount=20)
        self.assertEqual(dessert["title"], "8 damga topla, %20 indirim kazan")
        self.login(customer, "cust")
        self.scan(customer, owner, coffee["id"])
        # Each card has its own QR and its own stamps; the hourly limit is per card.
        self.scan(customer, owner, dessert["id"])
        self.call(customer, f"/api/card/{dessert['id']}/scan", {"scan_token": self.qr_token(owner, coffee["id"])}, 400)
        stamps = sorted((c["title"], c["stamps"]) for c in self.call(customer, "/api/me")["cards"])
        self.assertEqual(stamps, [("3 damga topla, 1 kahve bedava", 1), ("8 damga topla, %20 indirim kazan", 1)])
        metrics = self.call(owner, "/api/dashboard")["metrics"]
        self.assertEqual((metrics["customers"], metrics["visits"], metrics["returning"]), (1, 2, 1))
        listed = self.call(owner, "/api/programs")
        self.assertEqual(([p["customers"] for p in listed["programs"]], listed["max_active"]), ([1, 1], 5))

        for _ in range(3):
            self.new_card(owner)
        self.new_card(owner, expected=409)
        places = self.call(customer, "/api/places")["places"]
        self.assertEqual(len(places[0]["programs"]), 5)
        self.assertEqual(places[0]["programs"][0]["mine"], {"stamps": 1, "rewards_available": 0})

    def test_archived_card_stops_stamping_but_keeps_earned_rewards(self):
        owner, customer = self.client(), self.client()
        card_id = self.open_business(owner, "owner", required=2)["id"]
        self.login(customer, "cust")
        self.scan(customer, owner, card_id)
        self.age_stamps()
        self.assertTrue(self.scan(customer, owner, card_id)["earned_reward"])
        token = self.qr_token(owner, card_id)
        self.call(owner, f"/api/programs/{card_id}/archive", {"archived": True})
        self.call(owner, f"/api/programs/{card_id}/qr", expected=409)
        self.age_stamps()
        self.call(customer, f"/api/card/{card_id}/scan", {"scan_token": token}, 410)
        self.assertEqual(self.call(customer, "/api/places")["places"], [])
        # The customer still gets what they earned.
        self.call(customer, f"/api/card/{card_id}/redeem", {})
        self.call(owner, f"/api/redemptions/{self.call(owner, '/api/dashboard')['redemptions'][0]['id']}/approve", {})
        for _ in range(5):
            self.new_card(owner)
        self.call(owner, f"/api/programs/{card_id}/archive", {"archived": False}, 409)

    def test_reward_types_and_editing_keep_the_stamp_goal(self):
        owner = self.client()
        card = self.open_business(owner, "owner", required=6)
        for broken in ({"reward_type": "free", "reward_item": ""}, {"reward_type": "percent", "reward_amount": 3},
                       {"reward_type": "percent", "reward_amount": 101}, {"reward_type": "amount", "reward_amount": 0},
                       {"reward_type": "custom", "reward_title": " "}, {"reward_type": "bedava"}):
            self.call(owner, f"/api/programs/{card['id']}", broken, 400)
        self.new_card(owner, 1, 400)
        self.assertEqual(card["title"], "6 damga topla, 1 kahve bedava")
        edit = f"/api/programs/{card['id']}"
        percent = self.call(owner, edit, {"reward_type": "percent", "reward_amount": 20, "stamps_required": 9})["program"]
        self.assertEqual((percent["title"], percent["stamps_required"]), ("6 damga topla, %20 indirim kazan", 6))
        amount = self.call(owner, edit, {"reward_type": "amount", "reward_amount": 50})["program"]
        self.assertEqual(amount["title"], "6 damga topla, 50 ₺ indirim kazan")
        custom = self.call(owner, edit, {"reward_type": "custom", "reward_title": "Doğum gününde pasta"})["program"]
        self.assertEqual((custom["title"], custom["reward_amount"]), ("Doğum gününde pasta", 0))


class GuestStampTest(ServerTest):
    def test_first_stamp_without_sign_in_then_saved_to_google(self):
        owner, other, guest = self.client(), self.client(), self.client()
        card_id = self.open_business(owner, "owner")["id"]
        second_id = self.new_card(owner, 5)["id"]
        other_id = self.open_business(other, "other", "Diğer Kafe")["id"]
        first = self.scan(guest, owner, card_id)
        self.assertEqual((first["guest"], first["earned_reward"]), (True, False))
        self.assertEqual(self.call(guest, f"/api/card/{card_id}")["card"]["stamps"], 1)
        self.scan(guest, owner, second_id)  # another card of the same business is fine
        self.assertEqual(len(self.call(guest, "/api/me")["cards"]), 2)
        self.assertEqual(self.call(owner, "/api/dashboard")["recent"][0]["customer"], "Misafir")
        self.scan(guest, owner, card_id, 429)
        # One business only while signed out; rewards always need the account.
        self.scan(guest, other, other_id, 401)
        self.call(guest, f"/api/card/{card_id}/redeem", {}, 401)

        self.login(guest, "cust")
        me = self.call(guest, "/api/me")
        self.assertEqual((me["user"]["name"], sorted(c["stamps"] for c in me["cards"])), ("Test Kişi", [1, 1]))
        self.scan(guest, other, other_id)
        self.assertEqual(self.call(other, "/api/dashboard")["recent"][0]["customer"], "Test K.")

    def test_guest_stamps_never_add_to_an_existing_card(self):
        owner, phone, private_window = self.client(), self.client(), self.client()
        card_id = self.open_business(owner, "owner")["id"]
        self.login(phone, "cust")
        self.scan(phone, owner, card_id)
        self.scan(private_window, owner, card_id)
        self.login(private_window, "cust")
        self.assertEqual(self.call(private_window, f"/api/card/{card_id}")["card"]["stamps"], 1)

    def test_a_forged_guest_cookie_is_just_a_new_guest(self):
        owner, guest = self.client(), self.client()
        card_id = self.open_business(owner, "owner")["id"]
        self.set_cookie(guest, "loyalty_customer", "made-up")
        self.assertIsNone(self.call(guest, f"/api/card/{card_id}")["card"])
        self.scan(guest, owner, card_id)
        self.assertEqual(self.call(guest, f"/api/card/{card_id}")["card"]["stamps"], 1)


class ProfileAndMapTest(ServerTest):
    def test_profile_rules(self):
        owner = self.client()
        config.OPEN_SIGNUP = True
        self.login(owner, "owner", intent="merchant")
        base = {"business_name": "Kafe", "category": "Kafe", "address": "Moda", "lat": 40.9, "lng": 29.0}
        for broken in ({"lat": None}, {"lat": 0, "lng": 0}, {"lat": 91}, {"category": "Uzay"}, {"business_name": "  "}):
            self.call(owner, "/api/merchant", {**base, **broken}, 400)
        created = self.call(owner, "/api/merchant", base)["merchant"]
        updated = self.call(owner, "/api/merchant", {**base, "business_name": "Yeni Ad"})["merchant"]
        self.assertEqual((updated["slug"], updated["business_name"]), (created["slug"], "Yeni Ad"))

    def test_map_lists_places_with_cards_and_my_progress(self):
        owner, customer, guest = self.client(), self.client(), self.client()
        card_id = self.open_business(owner, "owner")["id"]
        self.sql("""INSERT INTO merchants(name,email,password_hash,business_name,slug,reward_title,stamps_required,
          created_at,lat,lng) VALUES('x','nocard@example.com','','Kartsız','kartsiz','',5,'2026-09-26',41,29)""")
        self.login(customer, "cust", intent="card", program=card_id, scan=self.qr_token(owner, card_id))
        places = self.call(guest, "/api/places")["places"]
        self.assertEqual([p["business_name"] for p in places], ["Nora Café"])
        self.assertIsNone(places[0]["programs"][0]["mine"])
        mine = self.call(customer, "/api/places")["places"][0]["programs"][0]["mine"]
        self.assertEqual(mine, {"stamps": 1, "rewards_available": 0})
        self.call(guest, "/api/geocode?q=Moda", expected=401)
        self.call(customer, "/api/geocode?q=a", expected=400)

    def test_demo_is_seeded_once_and_only_shown_in_demo_mode(self):
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
        self.assertEqual(len(self.call(browser, "/api/programs")["programs"]), 2)
        places = self.call(browser, "/api/places")["places"]
        self.assertEqual((len(places), sum(len(p["programs"]) for p in places)), (len(demo.DEMO_PLACES), 14))

    def test_asset_urls_carry_the_deploy_version(self):
        browser = self.client()
        page = self.open(browser, "/").read().decode()
        version = page.split("/styles.css?v=")[1][:10]
        self.assertIn(f'src="/js/main.js?v={version}"', page)
        main = self.open(browser, "/js/main.js").read().decode()
        self.assertIn(f'from "./nav.js?v={version}"', main)
        self.assertIn(f'import "./views/programs.js?v={version}"', main)
        self.assertIn(f'from "../api.js?v={version}"', self.open(browser, "/js/views/card.js").read().decode())
        self.assertEqual(self.open(browser, f"/styles.css?v={version}").status, 200)
        self.assertNotIn("?v=", self.open(browser, "/vendor/qrcode.min.js").read().decode()[:2000])

    def test_unknown_pages_get_the_404_page_and_unknown_api_gets_json(self):
        browser = self.client()
        for path in ("/yok", "/js/yok.js", "/kart/123"):
            response = self.open(browser, path)
            self.assertEqual((response.status, response.headers.get_content_type()), (404, "text/html"), path)
            self.assertIn("Bu sayfa kıyak yapamadı.", response.read().decode())
        api = self.open(browser, "/api/yok")
        self.assertEqual((api.status, api.headers.get_content_type()), (404, "application/json"))
        self.assertEqual(self.call(browser, "/api/card/999", expected=404)["error"], "Kart bulunamadı.")

    def test_showcase_places_are_labelled_and_do_not_open_the_demo_login(self):
        demo.seed_demo()
        self.open_business(self.client(), "real", "Gerçek Kafe")
        config.DEMO_PLACES = True
        browser = self.client()
        places = self.call(browser, "/api/places")["places"]
        shown = sorted((p["business_name"], p["demo"]) for p in places)
        self.assertEqual(shown.pop(0), ("Gerçek Kafe", False))
        self.assertEqual(shown, [("Köşe Fırın", True), ("Nergis Çiçekçilik", True), ("Nora Café", True),
                                 ("Usta Berber", True)])
        # Each sample place has its photo, and every photo is a file the site serves.
        photos = {p["business_name"]: p["photo"] for p in places}
        self.assertEqual(photos["Gerçek Kafe"], "")
        for name in ("Köşe Fırın", "Nergis Çiçekçilik", "Nora Café", "Usta Berber"):
            self.assertEqual(self.open(browser, photos[name]).headers["Content-Type"], "image/webp", name)
        self.call(browser, "/api/demo/login", {}, 404)

    def test_static_files_and_security_headers(self):
        browser = self.client()
        for path in ("/", "/js/main.js", "/styles.css", "/vendor/qrcode.min.js", "/vendor/maplibre/maplibre-gl.mjs",
                     "/fonts/sora-latin.woff2", "/manifest.webmanifest", "/brand/icon-192.png"):
            response = self.open(browser, path)
            self.assertEqual(response.status, 200, path)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertGreater(len(response.read()), 100, path)
        font = self.open(browser, "/fonts/sora-latin.woff2")
        self.assertEqual((font.headers["Content-Type"], font.headers["Cache-Control"]), ("font/woff2", "no-cache"))
        request = urllib.request.Request(self.base + "/styles.css", headers={"If-None-Match": font.headers["ETag"]})
        self.assertEqual(browser.open(request).status, 200)  # another file's tag does not match
        etag = self.open(browser, "/styles.css").headers["ETag"]
        with self.assertRaises(urllib.error.HTTPError) as unchanged:
            browser.open(urllib.request.Request(self.base + "/styles.css", headers={"If-None-Match": etag}))
        self.assertEqual(unchanged.exception.code, 304)
        self.assertEqual(self.open(browser, "/../bikiyak/config.py").status, 404)
        self.assertEqual(self.open(browser, "/api/me").headers["Cache-Control"], "no-store")
