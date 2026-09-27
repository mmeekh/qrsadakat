"""A real server on a temporary database, plus a stand-in for Google's token endpoint."""

from __future__ import annotations

import base64
import http.cookiejar
import json
import tempfile
import threading
import time
import unittest
from contextlib import closing
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from bikiyak import app, auth, config, db


class FakeGoogle:
    """Serves the token endpoint; each code returns the ID token claims registered for it."""

    def __init__(self):
        self.claims: dict[str, dict] = {}
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                form = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
                claims = fake.claims.pop(form["code"][0], None)
                body = b'{"error":"invalid_grant"}' if claims is None else json.dumps({"id_token": ".".join([
                    "e30", base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("="), "sig"])}).encode()
                self.send_response(400 if claims is None else 200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/token"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.saved = {name: getattr(config, name) for name in
                      ("DB_PATH", "DEMO_MODE", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "PUBLIC_URL", "OPEN_SIGNUP")}
        self.saved_token_url = auth.GOOGLE_TOKEN_URL
        self.temp = tempfile.TemporaryDirectory()
        config.DB_PATH = Path(self.temp.name) / "test.sqlite3"
        config.DEMO_MODE, config.PUBLIC_URL, config.OPEN_SIGNUP = False, "", False
        config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET = "test-client", "test-secret"
        self.google = FakeGoogle()
        auth.GOOGLE_TOKEN_URL = self.google.url
        db.migrate()
        handler = app.make_handler(app.build_router())
        handler.log_message = lambda *args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.google.server.shutdown()
        self.google.server.server_close()
        self.temp.cleanup()
        for name, value in self.saved.items():
            setattr(config, name, value)
        auth.GOOGLE_TOKEN_URL = self.saved_token_url

    def client(self):
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPCookieProcessor(jar))
        opener.jar = jar
        return opener

    def set_cookie(self, client, name, value):
        client.jar.set_cookie(http.cookiejar.Cookie(0, name, value, None, False, "127.0.0.1", False, False,
                                                    "/", True, False, None, False, None, None, {}))

    def open(self, client, path, data=None):
        request = urllib.request.Request(self.base + path, data=None if data is None else json.dumps(data).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            response = client.open(request)
        except urllib.error.HTTPError as error:
            response = error
        self.addCleanup(response.close)
        return response

    def call(self, client, path, data=None, expected=200):
        response = self.open(client, path, data)
        body = response.read().decode()
        self.assertEqual(response.status, expected, body)
        return json.loads(body)

    def login(self, client, sub, name="Test Kişi", email=None, intent="cards", program=None, scan=None, **claims):
        """Runs the whole Google round trip and returns where the callback redirected."""
        start = self.call(client, "/api/auth/start", {"intent": intent, "program": program, "scan_token": scan})
        query = parse_qs(urlsplit(start["url"]).query)
        code = "code-" + sub + str(time.monotonic())
        self.google.claims[code] = {"iss": "https://accounts.google.com", "aud": "test-client", "sub": sub,
                                    "email": email or f"{sub}@example.com", "email_verified": True, "name": name,
                                    "exp": time.time() + 300, "nonce": query["nonce"][0], **claims}
        response = self.open(client, "/auth/google/callback?" + urlencode({"code": code, "state": query["state"][0]}))
        self.assertEqual(response.status, 303)
        return response.headers["Location"], start

    def open_business(self, client, sub, name="Nora Café", required=2):
        """Signs in, opens a business and its first card; returns the card (program)."""
        self.sql("""INSERT INTO merchants(name,email,password_hash,business_name,slug,reward_title,stamps_required,
          created_at,category,address,lat,lng) VALUES(?,?,'',?,?,'',5,'2026-09-27','Kafe','Moda, Kadıköy',40.98,29.02)""",
                 (name, f"{sub}@example.com", name, f"slug-{sub}"))
        self.login(client, sub, intent="merchant")
        return self.new_card(client, required)

    def new_card(self, client, required=2, expected=200, **reward):
        body = {"reward_type": "free", "reward_item": "1 kahve", "stamps_required": required, **reward}
        return self.call(client, "/api/programs", body, expected).get("program")

    def qr_token(self, client, program_id):
        return self.call(client, f"/api/programs/{program_id}/qr")["scan_token"]

    def scan(self, client, owner, program_id, expected=200):
        return self.call(client, f"/api/card/{program_id}/scan", {"scan_token": self.qr_token(owner, program_id)}, expected)

    def sql(self, statement, params=()):
        with closing(db.connect()) as connection:
            connection.execute(statement, params)

    def age_stamps(self, hours=2):
        self.sql("UPDATE visits SET approved_at=datetime('now', ?) || '+00:00'", (f"-{hours} hours",))
