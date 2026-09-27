from __future__ import annotations

from contextlib import closing

from bikiyak import config, db, mail
from tests.harness import ServerTest


class WelcomeMailTest(ServerTest):
    def setUp(self):
        super().setUp()
        self.saved_mail = (config.WELCOME_MAIL, config.RESEND_API_KEY, mail.deliver, mail.RUN_INLINE)
        config.WELCOME_MAIL, config.RESEND_API_KEY, mail.RUN_INLINE = True, "re_test", True
        self.sent = []
        mail.deliver = lambda to, name="": self.sent.append((to, name)) or f"id-{len(self.sent)}"

    def tearDown(self):
        config.WELCOME_MAIL, config.RESEND_API_KEY, mail.deliver, mail.RUN_INLINE = self.saved_mail
        super().tearDown()

    def rows(self):
        with closing(db.connect()) as connection:
            return [tuple(r) for r in connection.execute("SELECT address, kind, status, provider_id FROM sent_mails")]

    def test_new_customer_gets_it_once(self):
        browser = self.client()
        self.login(browser, "ayse", name="Ayşe Yılmaz")
        self.login(browser, "ayse", name="Ayşe Yılmaz")
        self.assertEqual(self.sent, [("ayse@example.com", "Ayşe Yılmaz")])
        self.assertEqual(self.rows(), [("ayse@example.com", "welcome", "sent", "id-1")])

    def test_owners_and_disabled_flag_get_nothing(self):
        self.open_business(self.client(), "owner")
        config.WELCOME_MAIL = False
        self.login(self.client(), "later")
        self.assertEqual((self.sent, self.rows()), ([], []))

    def test_failure_is_recorded_not_raised(self):
        def broken(to, name=""):
            raise RuntimeError("Resend 422: domain not verified")
        mail.deliver = broken
        location, _ = self.login(self.client(), "cust")
        self.assertEqual(location, "/?view=cards")
        self.assertEqual(self.rows()[0][2], "failed")

    def test_render_escapes_name_and_links_to_the_site(self):
        subject, text, document = mail.render_welcome("<b>Ali</b> Veli")
        self.assertIn("Merhaba &lt;b&gt;Ali&lt;/b&gt;,", document)
        self.assertIn("Merhaba <b>Ali</b>,", text)
        self.assertIn("/?view=cards", document)
        self.assertIn("/gizlilik", document)
        self.assertIn("logo-ticket.png", document)  # no banner yet: logo band instead of a broken image
        self.assertEqual(mail.first_name("ayse@example.com"), "")
