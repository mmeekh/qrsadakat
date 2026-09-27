from __future__ import annotations

import contextlib
import io

from bikiyak import admin, config
from tests.harness import ServerTest

PROFILE = {"business_name": "Yeni Kafe", "category": "Kafe", "address": "Moda", "lat": 40.9, "lng": 29.0}


def run_admin(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = admin.main(list(args))
    return code, out.getvalue()


class InviteTest(ServerTest):
    def test_only_invited_emails_open_a_business(self):
        stranger, owner = self.client(), self.client()
        self.login(stranger, "stranger")
        self.assertFalse(self.call(stranger, "/api/me")["can_open_business"])
        error = self.call(stranger, "/api/merchant", PROFILE, 403)["error"]
        self.assertIn("stranger@example.com", error)

        self.assertEqual(run_admin("invite", "Owner@Example.com", "Nora", "Café")[0], 0)
        self.login(owner, "owner")
        self.assertTrue(self.call(owner, "/api/me")["can_open_business"])
        self.call(owner, "/api/merchant", PROFILE)
        # Editing an existing business never needs the invite again.
        self.assertEqual(run_admin("uninvite", "owner@example.com")[0], 0)
        self.call(owner, "/api/merchant", {**PROFILE, "business_name": "Adı değişti"})
        self.assertTrue(self.call(owner, "/api/me")["can_open_business"])

    def test_admin_listing_and_bad_input(self):
        run_admin("invite", "a@example.com", "A Fırın")
        owner = self.client()
        self.login(owner, "a")
        self.call(owner, "/api/merchant", PROFILE)
        run_admin("invite", "b@example.com")
        code, listing = run_admin("invites")
        self.assertEqual(code, 0)
        self.assertIn("a@example.com\tA Fırın", listing)
        self.assertIn("işletmesini açtı", listing)
        self.assertIn("b@example.com", listing)
        self.assertIn("2 davet", listing)
        self.assertEqual(run_admin("invite", "not-an-email")[0], 2)
        self.assertEqual(run_admin("nonsense")[0], 2)

    def test_open_signup_switch(self):
        config.OPEN_SIGNUP = True
        anyone = self.client()
        self.login(anyone, "anyone")
        self.call(anyone, "/api/merchant", PROFILE)
