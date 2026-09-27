"""The stamp card: rotating counter QR, stamps, rewards and the business dashboard."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from . import config
from .accounts import current_user, customer_for_user, guest_customer, new_guest, require_user, short_name
from .db import utcnow, write
from .merchants import merchant_by_slug, public_merchant, require_merchant
from .web import ApiError, Request, Response, Router

QR_SECRET = secrets.token_bytes(32)
routes = Router()


def make_scan_token(merchant_id: int, slot: int) -> str:
    message = f"{merchant_id}:{slot}".encode()
    # 96 bits is plenty for a code that lives 90 seconds, and keeps the QR less dense.
    return f"{slot}.{hmac.new(QR_SECRET, message, hashlib.sha256).hexdigest()[:24]}"


def valid_scan_token(merchant_id: int, token: str) -> bool:
    match = re.fullmatch(r"(\d{1,12})\.([a-f0-9]{24})", token)
    if not match:
        return False
    slot = int(match.group(1))
    now = time.time()
    current = int(now // 60)
    # Brief overlap lets a scan complete while the merchant QR rotates.
    if slot != current and not (slot == current - 1 and now % 60 < 30):
        return False
    return hmac.compare_digest(token, make_scan_token(merchant_id, slot))


def card_for(db: sqlite3.Connection, merchant_id: int, customer_id: int) -> sqlite3.Row:
    db.execute("INSERT OR IGNORE INTO cards(merchant_id,customer_id,created_at) VALUES(?,?,?)",
               (merchant_id, customer_id, utcnow()))
    return db.execute("SELECT * FROM cards WHERE merchant_id=? AND customer_id=?",
                      (merchant_id, customer_id)).fetchone()


def apply_stamp(db: sqlite3.Connection, merchant: sqlite3.Row, card: sqlite3.Row) -> bool:
    """Add one stamp inside the caller's write transaction; returns whether a reward opened."""
    last = db.execute("""SELECT approved_at FROM visits WHERE card_id=? AND status='approved'
      ORDER BY id DESC LIMIT 1""", (card["id"],)).fetchone()
    cooldown = timedelta(minutes=config.STAMP_COOLDOWN_MINUTES)
    if last and datetime.fromisoformat(last["approved_at"]) > datetime.now(timezone.utc) - cooldown:
        raise ApiError(429, "Bu kartın damgası zaten işlendi. Yeni damga için bir saat bekle.")
    stamped_at = utcnow()
    earned = card["stamps"] + 1 >= merchant["stamps_required"]
    db.execute("INSERT INTO visits(card_id,status,created_at,approved_at) VALUES(?,'approved',?,?)",
               (card["id"], stamped_at, stamped_at))
    db.execute("UPDATE cards SET visits=visits+1, stamps=?, rewards_available=rewards_available+? WHERE id=?",
               (0 if earned else card["stamps"] + 1, int(earned), card["id"]))
    return earned


def cards_of(db: sqlite3.Connection, customer_id: int | None) -> list[dict]:
    return [dict(r) for r in db.execute("""SELECT m.slug, m.business_name, m.reward_title, m.stamps_required,
      m.category, c.stamps, c.visits, c.rewards_available FROM cards c JOIN merchants m ON m.id=c.merchant_id
      WHERE c.customer_id=? AND (c.visits>0 OR c.rewards_available>0) ORDER BY c.id DESC""", (customer_id,))]


def guest_card(req: Request, response: Response, merchant: sqlite3.Row) -> sqlite3.Row:
    """A signed-out customer collects at one business; a second one needs Google sign-in."""
    customer = guest_customer(req) or new_guest(req, response)
    if req.db.execute("SELECT 1 FROM cards WHERE customer_id=? AND merchant_id<>? AND visits>0",
                      (customer, merchant["id"])).fetchone():
        raise ApiError(401, "Başka bir işletmede de damga toplamak için Google ile giriş yap; kartların hesabında birleşir.")
    return card_for(req.db, merchant["id"], customer)


@routes.get("/api/merchant/qr")
def counter_qr(req: Request) -> dict:
    merchant = require_merchant(req)
    now = time.time()
    slot = int(now // 60)
    return {"scan_token": make_scan_token(merchant["id"], slot),
            "refresh_in_ms": int(((slot + 1) * 60 - now) * 1000)}


@routes.get("/api/dashboard")
def dashboard(req: Request) -> dict:
    merchant = require_merchant(req)
    metrics = dict(req.db.execute("""SELECT COUNT(CASE WHEN visits > 0 THEN 1 END) AS customers,
      COALESCE(SUM(visits),0) AS visits, COALESCE(SUM(rewards_redeemed),0) AS redeemed,
      COALESCE(SUM(CASE WHEN visits >= 2 THEN 1 ELSE 0 END),0) AS returning_customers
      FROM cards WHERE merchant_id=?""", (merchant["id"],)).fetchone())
    # RETURNING is an SQL keyword in SQLite 3.35+, so the alias is renamed here.
    metrics["returning"] = metrics.pop("returning_customers")
    customer = """JOIN customers k ON k.id=c.customer_id LEFT JOIN users u ON u.id=k.user_id"""
    recent = [dict(r) for r in req.db.execute(f"""SELECT v.id, v.approved_at, c.id AS card_id, c.visits,
      COALESCE(u.name,'') AS customer FROM visits v JOIN cards c ON c.id=v.card_id {customer}
      WHERE c.merchant_id=? AND v.status='approved' ORDER BY v.id DESC LIMIT 8""", (merchant["id"],))]
    redemptions = [dict(r) for r in req.db.execute(f"""SELECT r.id, r.created_at, c.id AS card_id,
      COALESCE(u.name,'') AS customer FROM redemptions r JOIN cards c ON c.id=r.card_id {customer}
      WHERE c.merchant_id=? AND r.status='pending' ORDER BY r.id DESC""", (merchant["id"],))]
    for item in recent + redemptions:
        item["customer"] = short_name(item["customer"])
    return {"merchant": public_merchant(merchant), "metrics": metrics, "recent": recent, "redemptions": redemptions}


@routes.get("/api/card/{slug}")
def view_card(req: Request) -> dict:
    merchant = merchant_by_slug(req.db, req.params["slug"])
    user = current_user(req)
    if user:
        with write(req.db) as db:
            card = card_for(db, merchant["id"], customer_for_user(db, user["id"]))
    else:
        card = req.db.execute("SELECT * FROM cards WHERE merchant_id=? AND customer_id=?",
                              (merchant["id"], guest_customer(req))).fetchone()
    pending = card and req.db.execute("SELECT 1 FROM redemptions WHERE card_id=? AND status='pending'",
                                      (card["id"],)).fetchone()
    return {"merchant": public_merchant(merchant), "card": dict(card) if card else None,
            "redemption_pending": bool(pending), "guest": user is None}


@routes.post("/api/card/{slug}/scan")
def scan(req: Request) -> Response:
    user = current_user(req)
    merchant = merchant_by_slug(req.db, req.params["slug"])
    if not valid_scan_token(merchant["id"], str(req.body.get("scan_token", ""))):
        raise ApiError(400, "QR süresi dolmuş. İşletmedeki güncel QR kodunu okut.")
    response = Response()
    with write(req.db) as db:
        card = card_for(db, merchant["id"], customer_for_user(db, user["id"])) if user else guest_card(req, response, merchant)
        earned = apply_stamp(db, merchant, card)
    response.body = {"awarded": True, "earned_reward": earned, "guest": user is None}
    return response


@routes.post("/api/card/{slug}/redeem")
def redeem(req: Request) -> dict:
    user = require_user(req)
    merchant = merchant_by_slug(req.db, req.params["slug"])
    with write(req.db) as db:
        card = card_for(db, merchant["id"], customer_for_user(db, user["id"]))
        if card["rewards_available"] < 1:
            raise ApiError(409, "Kullanılabilir ödül yok.")
        if db.execute("SELECT 1 FROM redemptions WHERE card_id=? AND status='pending'", (card["id"],)).fetchone():
            raise ApiError(409, "Ödül onay bekliyor.")
        db.execute("INSERT INTO redemptions(card_id,status,created_at) VALUES(?,'pending',?)", (card["id"], utcnow()))
    return {"ok": True}


@routes.post("/api/redemptions/{id:int}/approve")
def approve_redemption(req: Request) -> dict:
    merchant = require_merchant(req)
    with write(req.db) as db:
        item = db.execute("""SELECT x.id, x.card_id, c.rewards_available FROM redemptions x
          JOIN cards c ON c.id=x.card_id WHERE x.id=? AND c.merchant_id=? AND x.status='pending'""",
                          (int(req.params["id"]), merchant["id"])).fetchone()
        if not item:
            raise ApiError(404, "Bekleyen istek bulunamadı.")
        if item["rewards_available"] < 1:
            raise ApiError(409, "Ödül artık kullanılamıyor.")
        db.execute("UPDATE redemptions SET status='approved', approved_at=? WHERE id=?", (utcnow(), item["id"]))
        db.execute("UPDATE cards SET rewards_available=rewards_available-1, rewards_redeemed=rewards_redeemed+1 "
                   "WHERE id=?", (item["card_id"],))
    return {"ok": True}
