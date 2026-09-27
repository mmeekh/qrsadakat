"""Demo mode (CHEABBY_DEMO_MODE=1): sample places and one-click access to Nora Café.
Turn it off for a real launch; demo places then disappear from the map."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone

from . import config
from .accounts import customer_for_user, start_session, upsert_user
from .db import connect, utcnow, write
from .web import ApiError, Request, Response, Router

DEMO_DOMAIN = "@mahalle.invalid"
DEMO_EMAIL = "demo" + DEMO_DOMAIN
# Coordinates are illustrative, not real businesses.
DEMO_PLACES = (
    {"email": DEMO_EMAIL, "business": "Nora Café", "slug": "nora-cafe-demo",
     "reward": "5 kahve al, 1 kahve bizden", "required": 5, "category": "Kafe",
     "address": "Moda, Kadıköy / İstanbul", "lat": 40.98372, "lng": 29.02683},
    {"email": "demo-firin" + DEMO_DOMAIN, "business": "Köşe Fırın", "slug": "kose-firin-demo",
     "reward": "10 poğaça al, 2 poğaça bizden", "required": 10, "category": "Fırın & pastane",
     "address": "Caferağa, Kadıköy / İstanbul", "lat": 40.98655, "lng": 29.02911},
    {"email": "demo-berber" + DEMO_DOMAIN, "business": "Usta Berber", "slug": "usta-berber-demo",
     "reward": "5 tıraş al, 6. tıraş bizden", "required": 5, "category": "Berber & kuaför",
     "address": "Osmanağa, Kadıköy / İstanbul", "lat": 40.98954, "lng": 29.02647},
)
DEMO_CUSTOMERS = (("Elif Kaya", 3, 3, 0), ("Mert Aydın", 6, 1, 1), ("Zeynep Tunç", 1, 1, 0))
routes = Router()


def seed_demo() -> None:
    """Create sample places once; later runs only fill fields older pilots lacked."""
    with closing(connect()) as db, write(db):
        for index, place in enumerate(DEMO_PLACES):
            owner_id = upsert_user(db, "demo:" + place["slug"], place["email"], "Demo İşletme", "")
            existing = db.execute("SELECT id FROM merchants WHERE email=?", (place["email"],)).fetchone()
            if existing:
                db.execute("""UPDATE merchants SET user_id=COALESCE(user_id,?),
                  category=CASE WHEN category='' THEN ? ELSE category END,
                  address=CASE WHEN address='' THEN ? ELSE address END,
                  lat=COALESCE(lat,?), lng=COALESCE(lng,?) WHERE id=?""",
                           (owner_id, place["category"], place["address"], place["lat"], place["lng"], existing["id"]))
                continue
            merchant_id = db.execute("""INSERT INTO merchants(name,email,password_hash,business_name,slug,
              reward_title,stamps_required,created_at,user_id,category,address,lat,lng)
              VALUES(?,?,'',?,?,?,?,?,?,?,?,?,?)""", (
                "Demo İşletme", place["email"], place["business"], place["slug"], place["reward"],
                place["required"], utcnow(), owner_id, place["category"], place["address"],
                place["lat"], place["lng"])).lastrowid
            if index == 0:
                seed_activity(db, merchant_id)


def seed_activity(db, merchant_id: int) -> None:
    for name, visits, stamps, available in DEMO_CUSTOMERS:
        user_id = upsert_user(db, "demo:customer:" + name, "musteri" + DEMO_DOMAIN, name, "")
        card_id = db.execute("""INSERT INTO cards(merchant_id,customer_id,stamps,visits,rewards_available,created_at)
          VALUES(?,?,?,?,?,?)""", (merchant_id, customer_for_user(db, user_id), stamps, visits,
                                   available, utcnow())).lastrowid
        for step in range(visits):
            stamped = (datetime.now(timezone.utc) - timedelta(days=visits - step)).isoformat(timespec="seconds")
            db.execute("INSERT INTO visits(card_id,status,created_at,approved_at) VALUES(?,'approved',?,?)",
                       (card_id, stamped, stamped))


@routes.post("/api/demo/login")
def demo_login(req: Request) -> Response:
    if not config.DEMO_MODE:
        raise ApiError(404, "Bulunamadı.")
    row = req.db.execute("SELECT user_id FROM merchants WHERE email=?", (DEMO_EMAIL,)).fetchone()
    if not row or not row["user_id"]:
        raise ApiError(503, "Demo henüz hazır değil.")
    response = Response({"ok": True})
    with write(req.db):
        start_session(req, response, row["user_id"])
    return response
