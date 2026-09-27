"""Sign in with Google (authorization code + PKCE) for customers and businesses alike.

A customer who scans the counter QR while signed out is sent to Google first; the QR is
checked when the sign-in starts and the stamp lands when Google sends them back."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.request
from urllib.parse import urlencode

from . import config
from .accounts import (adopt_guest, current_user, customer_for_user, customer_of, digest, public_user,
                       start_session, upsert_user)
from .db import write
from .loyalty import apply_stamp, card_for, cards_of, valid_scan_token
from .merchants import merchant_by_slug, merchant_of, public_merchant
from .web import ApiError, Request, Response, Router

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
BROWSER_COOKIE = "qr_oauth"
INTENTS = ("merchant", "card", "map", "cards", "account")
routes = Router()


class LoginError(Exception):
    pass


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def google_claims(code: str, verifier: str, redirect_uri: str, nonce: str) -> dict:
    """Exchange the code. The ID token comes straight from Google's token endpoint over
    TLS, so its signature needs no separate check (OpenID Connect Core 3.1.3.7)."""
    body = urlencode({"code": code, "client_id": config.GOOGLE_CLIENT_ID,
                      "client_secret": config.GOOGLE_CLIENT_SECRET, "redirect_uri": redirect_uri,
                      "grant_type": "authorization_code", "code_verifier": verifier}).encode()
    request = urllib.request.Request(GOOGLE_TOKEN_URL, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            token = json.loads(response.read(65_536))["id_token"]
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
        raise LoginError(type(error).__name__) from None
    audience = claims.get("aud")
    if (audience != config.GOOGLE_CLIENT_ID and not (isinstance(audience, list) and config.GOOGLE_CLIENT_ID in audience)) \
            or claims.get("iss") not in GOOGLE_ISSUERS \
            or not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < time.time() \
            or not hmac.compare_digest(str(claims.get("nonce", "")), nonce) \
            or claims.get("email_verified") is not True \
            or not isinstance(claims.get("sub"), str) or not isinstance(claims.get("email"), str):
        raise LoginError("claims")
    return claims


@routes.post("/api/auth/start")
def start(req: Request) -> Response:
    if not config.google_enabled():
        raise ApiError(503, "Google girişi henüz yapılandırılmadı.")
    intent = str(req.body.get("intent", ""))
    if intent not in INTENTS:
        raise ApiError(400, "Geçersiz giriş isteği.")
    slug, scan_ok = None, False
    if intent == "card":
        merchant = merchant_by_slug(req.db, str(req.body.get("slug", "")))
        slug = merchant["slug"]
        # Checked now, while the QR is fresh; Google may take longer than the QR lives.
        scan_ok = valid_scan_token(merchant["id"], str(req.body.get("scan_token", "")))
    state, verifier, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(64), secrets.token_urlsafe(16)
    browser = req.cookie(BROWSER_COOKIE)
    if not browser or not re.fullmatch(r"[A-Za-z0-9_-]{43}", browser):
        browser = secrets.token_urlsafe(32)
    with write(req.db) as db:
        db.execute("DELETE FROM oauth_states WHERE created_at<?", (time.time() - config.OAUTH_STATE_SECONDS,))
        db.execute("""INSERT INTO oauth_states(state_hash,browser_hash,verifier,nonce,intent,slug,scan_ok,created_at)
          VALUES(?,?,?,?,?,?,?,?)""", (digest(state), digest(browser), verifier, nonce, intent, slug,
                                       int(scan_ok), time.time()))
    url = GOOGLE_AUTH_URL + "?" + urlencode({
        "client_id": config.GOOGLE_CLIENT_ID, "redirect_uri": req.origin() + "/auth/google/callback",
        "response_type": "code", "scope": "openid email profile", "state": state, "nonce": nonce,
        "code_challenge": b64url(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256"})
    response = Response({"url": url, "scan_ok": scan_ok})
    req.set_cookie(response, BROWSER_COOKIE, browser, config.OAUTH_STATE_SECONDS)
    return response


@routes.get("/auth/google/callback")
def callback(req: Request) -> Response:
    with write(req.db) as db:
        row = db.execute("SELECT * FROM oauth_states WHERE state_hash=?", (digest(req.arg("state")),)).fetchone()
        if row:
            # One use only, even when the exchange below fails.
            db.execute("DELETE FROM oauth_states WHERE state_hash=?", (row["state_hash"],))
    if not row or row["created_at"] < time.time() - config.OAUTH_STATE_SECONDS \
            or not hmac.compare_digest(row["browser_hash"], digest(req.cookie(BROWSER_COOKIE) or "")):
        return finish(req, Response.redirect("/?login=failed"))
    back = f"/?c={row['slug']}" if row["intent"] == "card" else f"/?view={row['intent']}"
    if not req.arg("code"):
        return finish(req, Response.redirect(back + "&login=cancelled"))
    try:
        claims = google_claims(req.arg("code"), row["verifier"], req.origin() + "/auth/google/callback", row["nonce"])
    except LoginError as error:
        print(f"Google sign-in failed: {error}", flush=True)
        return finish(req, Response.redirect(back + "&login=failed"))

    response = Response.redirect(back)
    with write(req.db) as db:
        user_id = sign_in(req, response, claims)
        if row["intent"] == "card" and row["scan_ok"]:
            merchant = merchant_by_slug(db, row["slug"])
            try:
                earned = apply_stamp(db, merchant, card_for(db, merchant["id"], customer_for_user(db, user_id)))
                response.location += "&stamp=" + ("reward" if earned else "ok")
            except ApiError:
                response.location += "&stamp=wait"
    return finish(req, response)


def finish(req: Request, response: Response) -> Response:
    req.set_cookie(response, BROWSER_COOKIE, "", 0)
    return response


def sign_in(req: Request, response: Response, claims: dict) -> int:
    """Create or refresh the account, then carry over anything from before Google sign-in."""
    db = req.db
    email = claims["email"].strip().lower()[:254]
    name = " ".join(str(claims.get("name") or email.split("@")[0]).split())[:80]
    picture = str(claims.get("picture", ""))
    picture = picture[:500] if re.fullmatch(r"https://[a-z0-9.-]+\.googleusercontent\.com/\S*", picture) else ""
    user_id = upsert_user(db, claims["sub"], email, name, picture)
    if not merchant_of(db, user_id):
        # A business opened with e-mail and password in the first pilot joins its owner's account.
        db.execute("""UPDATE merchants SET user_id=? WHERE id=(SELECT id FROM merchants
          WHERE user_id IS NULL AND lower(email)=? LIMIT 1)""", (user_id, email))
    adopt_guest(req, response, user_id)
    start_session(req, response, user_id)
    return user_id


@routes.get("/api/me")
def me(req: Request) -> dict:
    user = current_user(req)
    cards = cards_of(req.db, customer_of(req, user))
    if not user:
        # A guest sees their one card, with a prompt to save it to a Google account.
        return {"user": None, "merchant": None, "cards": cards}
    merchant = merchant_of(req.db, user["id"])
    return {"user": public_user(user), "merchant": public_merchant(merchant) if merchant else None, "cards": cards}
