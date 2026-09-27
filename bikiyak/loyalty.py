"""The stamp card: each reward card's rotating counter QR, stamps, rewards and the dashboard."""

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
from .merchants import merchant_by_id, public_merchant, require_merchant
from .programs import own_program, program_by_id, public_program
from .web import ApiError, Request, Response, Router

QR_SECRET = secrets.token_bytes(32)
routes = Router()


def make_scan_token(program_id: int, slot: int) -> str:
    message = f"program:{program_id}:{slot}".encode()
    # 96 bits is plenty for a code that lives 90 seconds, and keeps the QR less dense.
    return f"{slot}.{hmac.new(QR_SECRET, message, hashlib.sha256).hexdigest()[:24]}"


def valid_scan_token(program_id: int, token: str) -> bool:
    match = re.fullmatch(r"(\d{1,12})\.([a-f0-9]{24})", token)
    if not match:
        return False
    slot = int(match.group(1))
    now = time.time()
    current = int(now // 60)
    # Brief overlap lets a scan complete while the merchant QR rotates.
    if slot != current and not (slot == current - 1 and now % 60 < 30):
        return False
    return hmac.compare_digest(token, make_scan_token(program_id, slot))


def card_for(db: sqlite3.Connection, program: sqlite3.Row, customer_id: int) -> sqlite3.Row:
    db.execute("INSERT OR IGNORE INTO cards(program_id,merchant_id,customer_id,created_at) VALUES(?,?,?,?)",
               (program["id"], program["merchant_id"], customer_id, utcnow()))
    return db.execute("SELECT * FROM cards WHERE program_id=? AND customer_id=?",
                      (program["id"], customer_id)).fetchone()


def apply_stamp(db: sqlite3.Connection, program: sqlite3.Row, card: sqlite3.Row) -> bool:
    """Add one stamp inside the caller's write transaction; returns whether a reward opened."""
    if program["archived_at"]:
        raise ApiError(410, "Bu kart artık damga vermiyor.")
    last = db.execute("""SELECT approved_at FROM visits WHERE card_id=? AND status='approved'
      ORDER BY id DESC LIMIT 1""", (card["id"],)).fetchone()
    cooldown = timedelta(minutes=config.STAMP_COOLDOWN_MINUTES)
    if last and datetime.fromisoformat(last["approved_at"]) > datetime.now(timezone.utc) - cooldown:
        raise ApiError(429, "Bu kartın damgası zaten işlendi. Yeni damga için bir saat bekle.")
    stamped_at = utcnow()
    earned = card["stamps"] + 1 >= program["stamps_required"]
    db.execute("INSERT INTO visits(card_id,status,created_at,approved_at) VALUES(?,'approved',?,?)",
               (card["id"], stamped_at, stamped_at))
    db.execute("UPDATE cards SET visits=visits+1, stamps=?, rewards_available=rewards_available+? WHERE id=?",
               (0 if earned else card["stamps"] + 1, int(earned), card["id"]))
    return earned


def cards_of(db: sqlite3.Connection, customer_id: int | None) -> list[dict]:
    return [dict(r) for r in db.execute("""SELECT p.id AS program_id, p.title, p.stamps_required,
      p.archived_at IS NOT NULL AS archived, m.business_name, m.category, c.stamps, c.visits, c.rewards_available
      FROM cards c JOIN programs p ON p.id=c.program_id JOIN merchants m ON m.id=c.merchant_id
      WHERE c.customer_id=? AND (c.visits>0 OR c.rewards_available>0) ORDER BY c.id DESC""", (customer_id,))]


def guest_card(req: Request, response: Response, program: sqlite3.Row) -> sqlite3.Row:
    """A signed-out customer collects at one business (any of its cards); a second needs Google."""
    customer = guest_customer(req) or new_guest(req, response)
    if req.db.execute("SELECT 1 FROM cards WHERE customer_id=? AND merchant_id<>? AND visits>0",
                      (customer, program["merchant_id"])).fetchone():
        raise ApiError(401, "Başka bir işletmede de damga toplamak için Google ile giriş yap; kartların hesabında birleşir.")
    return card_for(req.db, program, customer)


@routes.get("/api/programs/{id:int}/qr")
def counter_qr(req: Request) -> dict:
    _, program = own_program(req)
    if program["archived_at"]:
        raise ApiError(409, "Arşivdeki kart damga vermez.")
    now = time.time()
    slot = int(now // 60)
    return {"scan_token": make_scan_token(program["id"], slot), "refresh_in_ms": int(((slot + 1) * 60 - now) * 1000)}


@routes.get("/api/dashboard")
def dashboard(req: Request) -> dict:
    merchant = require_merchant(req)
    # One customer may hold several of this business's cards, so count people, not cards.
    metrics = dict(req.db.execute("""SELECT COUNT(*) AS customers, COALESCE(SUM(v),0) AS visits,
      COALESCE(SUM(r),0) AS redeemed, COALESCE(SUM(v >= 2),0) AS returning_customers
      FROM (SELECT SUM(visits) AS v, SUM(rewards_redeemed) AS r FROM cards WHERE merchant_id=?
            GROUP BY customer_id HAVING SUM(visits) > 0)""", (merchant["id"],)).fetchone())
    # RETURNING is an SQL keyword in SQLite 3.35+, so the alias is renamed here.
    metrics["returning"] = metrics.pop("returning_customers")
    joins = """JOIN programs p ON p.id=c.program_id JOIN customers k ON k.id=c.customer_id
      LEFT JOIN users u ON u.id=k.user_id"""
    recent = [dict(r) for r in req.db.execute(f"""SELECT v.id, v.approved_at, c.id AS card_id, c.visits,
      p.title AS program, COALESCE(u.name,'') AS customer FROM visits v JOIN cards c ON c.id=v.card_id {joins}
      WHERE c.merchant_id=? AND v.status='approved' ORDER BY v.id DESC LIMIT 8""", (merchant["id"],))]
    redemptions = [dict(r) for r in req.db.execute(f"""SELECT r.id, r.created_at, c.id AS card_id,
      p.title AS program, COALESCE(u.name,'') AS customer FROM redemptions r JOIN cards c ON c.id=r.card_id {joins}
      WHERE c.merchant_id=? AND r.status='pending' ORDER BY r.id DESC""", (merchant["id"],))]
    for item in recent + redemptions:
        item["customer"] = short_name(item["customer"])
    return {"merchant": public_merchant(merchant), "metrics": metrics, "recent": recent, "redemptions": redemptions}


@routes.get("/api/card/{id:int}")
def view_card(req: Request) -> dict:
    program = program_by_id(req.db, int(req.params["id"]))
    user = current_user(req)
    if user:
        with write(req.db) as db:
            card = card_for(db, program, customer_for_user(db, user["id"]))
    else:
        card = req.db.execute("SELECT * FROM cards WHERE program_id=? AND customer_id=?",
                              (program["id"], guest_customer(req))).fetchone()
    pending = card and req.db.execute("SELECT 1 FROM redemptions WHERE card_id=? AND status='pending'",
                                      (card["id"],)).fetchone()
    return {"merchant": public_merchant(merchant_by_id(req.db, program["merchant_id"])),
            "program": public_program(program), "card": dict(card) if card else None,
            "redemption_pending": bool(pending), "guest": user is None}


@routes.post("/api/card/{id:int}/scan")
def scan(req: Request) -> Response:
    user = current_user(req)
    program = program_by_id(req.db, int(req.params["id"]))
    if not valid_scan_token(program["id"], str(req.body.get("scan_token", ""))):
        raise ApiError(400, "QR süresi dolmuş. İşletmedeki güncel QR kodunu okut.")
    response = Response()
    with write(req.db) as db:
        card = card_for(db, program, customer_for_user(db, user["id"])) if user else guest_card(req, response, program)
        earned = apply_stamp(db, program, card)
    response.body = {"awarded": True, "earned_reward": earned, "guest": user is None}
    return response


@routes.post("/api/card/{id:int}/redeem")
def redeem(req: Request) -> dict:
    user = require_user(req)
    program = program_by_id(req.db, int(req.params["id"]))
    with write(req.db) as db:
        card = card_for(db, program, customer_for_user(db, user["id"]))
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
