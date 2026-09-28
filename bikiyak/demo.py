"""Demo mode (BIKIYAK_DEMO_MODE=1): sample places and one-click access to Nora Café.
Turn it off for a real launch; demo places then disappear from the map."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone

from . import config
from .accounts import customer_for_user, start_session, upsert_user
from .db import connect, utcnow, write
from .programs import insert_program
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
) + tuple(
    # Fictional places across Turkey so the map shows every category; names are generic.
    {"email": f"demo-{slug}{DEMO_DOMAIN}", "slug": f"{slug}-demo", "business": business, "category": category,
     "reward": reward, "required": required, "address": address, "lat": lat, "lng": lng}
    for slug, business, category, reward, required, address, lat, lng in (
        ("kordon-kahve", "Kordon Kahve Evi", "Kafe", "6 kahve al, 1 kahve bizden", 6,
         "Alsancak, Konak / İzmir", 38.43702, 27.14298),
        ("ev-yemekleri", "Ev Yemekleri Lokantası", "Restoran", "8 öğle yemeği, 1 tatlı bizden", 8,
         "Kızılay, Çankaya / Ankara", 39.92081, 32.85412),
        ("mahalle-firini", "Mahalle Fırını", "Fırın & pastane", "10 simit al, 1 simit bizden", 10,
         "Osmangazi / Bursa", 40.18852, 29.06103),
        ("bereket-bakkal", "Bereket Bakkal", "Market", "10 alışveriş, 1 ekmek bizden", 10,
         "Odunpazarı / Eskişehir", 39.76671, 30.52559),
        ("makas-berber", "Makas Berber", "Berber & kuaför", "5 tıraş al, 6. tıraş bizden", 5,
         "Muratpaşa / Antalya", 36.88413, 30.70561),
        ("liman-cay", "Liman Çay Bahçesi", "Kafe", "7 çay al, 1 çay bizden", 7,
         "Ortahisar / Trabzon", 41.00268, 39.71679),
        ("kebap-kosesi", "Kebap Köşesi", "Restoran", "6 porsiyon, 1 künefe bizden", 6,
         "Şahinbey / Gaziantep", 37.06622, 37.38331),
        ("nergis-cicek", "Nergis Çiçekçilik", "Diğer", "5 buket al, 1 saksı çiçeği bizden", 5,
         "Beşiktaş / İstanbul", 41.04302, 29.00697),
        ("kitap-kafe", "Kitap Kafe", "Kafe", "5 kahve al, 1 kurabiye bizden", 5,
         "Selçuklu / Konya", 37.87461, 32.49318),
        ("taze-manav", "Taze Manav", "Market", "8 alışveriş, 1 kg meyve bizden", 8,
         "Seyhan / Adana", 36.99142, 35.33083),
    )
)
# Four neighbouring Istanbul places shown on the live map when BIKIYAK_DEMO_PLACES=1.
SHOWCASE = ("nora-cafe-demo", "kose-firin-demo", "usta-berber-demo", "nergis-cicek-demo")
DEMO_CUSTOMERS = (("Elif Kaya", 3, 3, 0), ("Mert Aydın", 6, 1, 1), ("Zeynep Tunç", 1, 1, 0))
# Nora Café shows that one business can run several cards.
EXTRA_CARDS = {"nora-cafe-demo": (({"reward_type": "percent", "reward_item": "", "reward_amount": 20, "custom": ""}, 8),)}
routes = Router()


def seed_demo() -> None:
    """Create sample places once; later runs only fill what older pilots lacked (owner, pin, cards)."""
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
                seed_cards(db, existing["id"], place)
                continue
            merchant_id = db.execute("""INSERT INTO merchants(name,email,password_hash,business_name,slug,
              reward_title,stamps_required,created_at,user_id,category,address,lat,lng)
              VALUES(?,?,'',?,?,?,?,?,?,?,?,?,?)""", (
                "Demo İşletme", place["email"], place["business"], place["slug"], place["reward"],
                place["required"], utcnow(), owner_id, place["category"], place["address"],
                place["lat"], place["lng"])).lastrowid
            seed_cards(db, merchant_id, place)
            if index == 0:
                seed_activity(db, merchant_id)


def seed_cards(db, merchant_id: int, place: dict) -> None:
    """Adds the place's cards it does not have yet, counted by position, so edits made
    through the demo panel are not duplicated on restart."""
    cards = ((({"reward_type": "custom", "reward_item": "", "reward_amount": 0, "custom": place["reward"]},
               place["required"]),) + EXTRA_CARDS.get(place["slug"], ()))
    have = db.execute("SELECT COUNT(*) FROM programs WHERE merchant_id=?", (merchant_id,)).fetchone()[0]
    for reward, required in cards[have:]:
        insert_program(db, merchant_id, reward, required)


def seed_activity(db, merchant_id: int) -> None:
    program = db.execute("SELECT id FROM programs WHERE merchant_id=? ORDER BY id LIMIT 1", (merchant_id,)).fetchone()
    for name, visits, stamps, available in DEMO_CUSTOMERS:
        user_id = upsert_user(db, "demo:customer:" + name, "musteri" + DEMO_DOMAIN, name, "")
        card_id = db.execute("""INSERT INTO cards(program_id,merchant_id,customer_id,stamps,visits,rewards_available,
          created_at) VALUES(?,?,?,?,?,?,?)""", (program["id"], merchant_id, customer_for_user(db, user_id), stamps,
                                                  visits, available, utcnow())).lastrowid
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
