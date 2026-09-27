from __future__ import annotations

import contextlib
import io

from bikiyak import admin, config, places
from tests.harness import ServerTest

PROFILE = {"business_name": "Yeni Kafe", "category": "Kafe", "address": "Moda", "lat": 40.9, "lng": 29.0}


def run_admin(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = admin.main(list(args))
    return code, out.getvalue()


class AddMerchantTest(ServerTest):
    def test_operator_adds_business_and_owner_lands_on_it_at_first_sign_in(self):
        code, out = run_admin("add-merchant", "Owner@Example.com", "Nora Café", "Kafe", "Moda, Kadıköy", "40.98", "29.02")
        self.assertEqual(code, 0, out)
        self.assertIn("ilk girişte bağlanacak", out)
        owner = self.client()
        self.login(owner, "owner")
        me = self.call(owner, "/api/me")
        self.assertEqual((me["merchant"]["business_name"], me["merchant"]["lat"]), ("Nora Café", 40.98))
        card = self.new_card(owner, 5)
        self.assertEqual(len(self.call(self.client(), "/api/places")["places"]), 1)
        self.assertEqual(card["title"], "5 damga topla, 1 kahve bedava")

    def test_existing_customer_is_linked_right_away(self):
        customer = self.client()
        self.login(customer, "ayse")
        self.assertIsNone(self.call(customer, "/api/me")["merchant"])
        code, out = run_admin("add-merchant", "ayse@example.com", "Ayşe Fırın", "Fırın & pastane", "Bursa", "40.18", "29.06")
        self.assertIn("hemen bağlandı", out)
        self.assertEqual(self.call(customer, "/api/me")["merchant"]["business_name"], "Ayşe Fırın")

    def test_rejects_duplicates_bad_input_and_geocodes_addresses(self):
        run_admin("add-merchant", "a@example.com", "A", "Kafe", "X", "41", "29")
        self.assertEqual(run_admin("add-merchant", "a@example.com", "B", "Kafe", "Y", "41", "29")[0], 1)
        code, out = run_admin("add-merchant", "b@example.com", "B", "Uzay", "Y", "41", "29")
        self.assertEqual(code, 2)
        self.assertIn("Kafe", out)
        self.assertEqual(run_admin("add-merchant", "not-an-email", "B", "Kafe", "Y")[0], 2)
        original = places.geocode
        places.geocode = lambda query: [{"label": "Moda, Kadıköy", "lat": 40.98, "lng": 29.02}]
        try:
            code, out = run_admin("add-merchant", "c@example.com", "C Kafe", "Kafe", "Moda Cd. 12")
        finally:
            places.geocode = original
        self.assertEqual(code, 0, out)
        self.assertIn("40.98000", out)
        listing = run_admin("merchants")[1]
        self.assertIn("c@example.com\tC Kafe\tKafe\thenüz girmedi\t0 aktif kart", listing)
        self.assertIn("2 işletme", listing)

    def test_site_does_not_let_customers_open_a_business(self):
        stranger = self.client()
        self.login(stranger, "stranger")
        self.assertFalse(self.call(stranger, "/api/me")["can_open_business"])
        self.assertIn("stranger@example.com", self.call(stranger, "/api/merchant", PROFILE, 403)["error"])
        config.OPEN_SIGNUP = True
        self.call(stranger, "/api/merchant", PROFILE)


class PrivacyPageTest(ServerTest):
    def test_privacy_page_is_public_and_linked_from_home(self):
        browser = self.client()
        page = self.open(browser, "/gizlilik")
        self.assertEqual(page.status, 200)
        body = page.read().decode()
        self.assertIn("KVKK", body)
        self.assertIn("iletisim@xn--bikyak-r9a.com", body)
        self.assertNotIn("[[", body)
        self.assertIn('href="/gizlilik"', self.open(browser, "/").read().decode())
