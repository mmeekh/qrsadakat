"""Small, dependency-free QR loyalty pilot. Run: python server.py"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("LOYALTY_DB", str(ROOT / "pilot.sqlite3")))
HOST = os.environ.get("LOYALTY_HOST", "127.0.0.1")
PORT = int(os.environ.get("LOYALTY_PORT", "8088"))
MAX_BODY = 16_384
SESSION_DAYS = 30
DEMO_MODE = os.environ.get("LOYALTY_DEMO_MODE", "0") == "1"
DEMO_EMAIL = "demo@mahalle.invalid"
QR_SECRET = secrets.token_bytes(32)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS merchants (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, business_name TEXT NOT NULL,
          slug TEXT NOT NULL UNIQUE, reward_title TEXT NOT NULL,
          stamps_required INTEGER NOT NULL CHECK(stamps_required BETWEEN 2 AND 20),
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, merchant_id INTEGER NOT NULL REFERENCES merchants(id),
          expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS customers (
          id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cards (
          id INTEGER PRIMARY KEY, merchant_id INTEGER NOT NULL REFERENCES merchants(id),
          customer_id INTEGER NOT NULL REFERENCES customers(id), stamps INTEGER NOT NULL DEFAULT 0,
          visits INTEGER NOT NULL DEFAULT 0, rewards_available INTEGER NOT NULL DEFAULT 0,
          rewards_redeemed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
          UNIQUE(merchant_id, customer_id)
        );
        CREATE TABLE IF NOT EXISTS visits (
          id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id),
          status TEXT NOT NULL CHECK(status IN ('pending','approved')),
          created_at TEXT NOT NULL, approved_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_pending_visit ON visits(card_id) WHERE status='pending';
        CREATE TABLE IF NOT EXISTS redemptions (
          id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id),
          status TEXT NOT NULL CHECK(status IN ('pending','approved')),
          created_at TEXT NOT NULL, approved_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_pending_redemption ON redemptions(card_id) WHERE status='pending';
        """)


def seed_demo() -> None:
    """Create sample activity once; never reset a demo that someone has used."""
    with closing(connect()) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM merchants WHERE email=?", (DEMO_EMAIL,)).fetchone():
            return
        merchant_id = db.execute("""INSERT INTO merchants
            (name,email,password_hash,business_name,slug,reward_title,stamps_required,created_at)
            VALUES(?,?,?,?,?,?,?,?)""", (
            "Demo İşletme", DEMO_EMAIL, password_hash(secrets.token_urlsafe(24)),
            "Nora Café", "nora-cafe-demo", "5 kahve al, 1 kahve bizden", 5, utcnow(),
        )).lastrowid
        for visits, stamps, available in ((3, 3, 0), (6, 1, 1), (1, 1, 0)):
            customer_id = db.execute("INSERT INTO customers(token_hash,created_at) VALUES(?,?)",
                                     (digest(secrets.token_urlsafe(32)), utcnow())).lastrowid
            card_id = db.execute("""INSERT INTO cards
                (merchant_id,customer_id,stamps,visits,rewards_available,created_at)
                VALUES(?,?,?,?,?,?)""", (merchant_id, customer_id, stamps, visits, available, utcnow())).lastrowid
            for index in range(visits):
                timestamp = (datetime.now(timezone.utc) - timedelta(days=visits - index)).isoformat(timespec="seconds")
                db.execute("""INSERT INTO visits(card_id,status,created_at,approved_at)
                    VALUES(?,'approved',?,?)""", (card_id, timestamp, timestamp))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def make_scan_token(merchant_id: int, slot: int) -> str:
    message = f"{merchant_id}:{slot}".encode()
    return f"{slot}.{hmac.new(QR_SECRET, message, hashlib.sha256).hexdigest()}"


def valid_scan_token(merchant_id: int, token: str) -> bool:
    match = re.fullmatch(r"(\d{1,12})\.([a-f0-9]{64})", token)
    if not match:
        return False
    slot = int(match.group(1))
    now = time.time()
    current = int(now // 60)
    # Brief overlap lets a scan complete while the merchant QR rotates or
    # the customer's first visit passes through the Caddy login prompt.
    if slot != current and not (slot == current - 1 and now % 60 < 30):
        return False
    return hmac.compare_digest(token, make_scan_token(merchant_id, slot))


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"{salt.hex()}:{key.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        salt, wanted = stored.split(":", 1)
        key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(key, bytes.fromhex(wanted))
    except (ValueError, TypeError):
        return False


def public_merchant(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in ("id", "name", "business_name", "slug", "reward_title", "stamps_required")}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


class Handler(BaseHTTPRequestHandler):
    server_version = "SadakatPilot/0.1"

    def respond(self, status: int, value: object, cookie: str | None = None) -> None:
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def respond_committed(self, db: sqlite3.Connection, status: int, value: object,
                          cookie: str | None = None) -> None:
        # The client can send its next request as soon as the body arrives.
        db.commit()
        self.respond(status, value, cookie)

    def send_file(self, filename: str, mime: str) -> None:
        body = (ROOT / "static" / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def cookie_value(self, name: str) -> str | None:
        try:
            jar = SimpleCookie(self.headers.get("Cookie", ""))
            return jar[name].value if name in jar else None
        except Exception:
            return None

    def cookie_header(self, name: str, value: str, max_age: int) -> str:
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        return f"{name}={value}; HttpOnly; SameSite=Lax; Path=/; Max-Age={max_age}{secure}"

    def json_body(self) -> dict:
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ApiError(415, "JSON bekleniyor.")
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise ApiError(413, "İstek çok büyük.")
        try:
            value = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "Geçersiz JSON.")
        if not isinstance(value, dict):
            raise ApiError(400, "Nesne bekleniyor.")
        return value

    def merchant(self, db: sqlite3.Connection) -> sqlite3.Row:
        token = self.cookie_value("loyalty_session")
        row = db.execute("""SELECT m.* FROM merchants m JOIN sessions s ON s.merchant_id=m.id
          WHERE s.token_hash=? AND s.expires_at>?""", (digest(token or ""), utcnow())).fetchone()
        if not row:
            raise ApiError(401, "Oturum açmanız gerekiyor.")
        return row

    def card(self, db: sqlite3.Connection, slug: str) -> tuple[sqlite3.Row, sqlite3.Row, str | None]:
        merchant = db.execute("SELECT * FROM merchants WHERE slug=?", (slug,)).fetchone()
        if not merchant:
            raise ApiError(404, "İşletme bulunamadı.")
        token = self.cookie_value("loyalty_customer")
        customer = db.execute("SELECT id FROM customers WHERE token_hash=?", (digest(token or ""),)).fetchone()
        cookie = None
        if not customer:
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO customers(token_hash,created_at) VALUES(?,?)", (digest(token), utcnow()))
            customer = db.execute("SELECT last_insert_rowid() AS id").fetchone()
            cookie = self.cookie_header("loyalty_customer", token, 365 * 86400)
        db.execute("INSERT OR IGNORE INTO cards(merchant_id,customer_id,created_at) VALUES(?,?,?)",
                   (merchant["id"], customer["id"], utcnow()))
        card = db.execute("SELECT * FROM cards WHERE merchant_id=? AND customer_id=?",
                          (merchant["id"], customer["id"])).fetchone()
        return merchant, card, cookie

    def route(self) -> None:
        path = urlsplit(self.path).path
        if self.command == "GET" and path in ("/", "/index.html"):
            return self.send_file("index.html", "text/html; charset=utf-8")
        if self.command == "GET" and path in ("/app.js", "/styles.css", "/qrcode.min.js", "/cafe-card-bg.webp", "/shop-card-bg.webp"):
            mime = "image/webp" if path.endswith(".webp") else "text/css; charset=utf-8" if path.endswith(".css") else "text/javascript; charset=utf-8"
            return self.send_file(path[1:], mime)
        if not path.startswith("/api/"):
            raise ApiError(404, "Sayfa bulunamadı.")
        if path == "/api/config" and self.command == "GET":
            return self.respond(200, {"demo_enabled": DEMO_MODE})
        if self.command == "POST":
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            if origin and urlsplit(origin).netloc != host:
                raise ApiError(403, "İstek kaynağı geçersiz.")
            data = self.json_body()
        else:
            data = {}
        with closing(connect()) as db, db:
            if path == "/api/demo/login" and self.command == "POST" and DEMO_MODE:
                row = db.execute("SELECT id FROM merchants WHERE email=?", (DEMO_EMAIL,)).fetchone()
                if not row:
                    raise ApiError(503, "Demo henüz hazır değil.")
                return self.start_session(db, row["id"])

            if path == "/api/register" and self.command == "POST":
                name = str(data.get("name", "")).strip()[:80]
                business = str(data.get("business_name", "")).strip()[:80]
                email = str(data.get("email", "")).strip().lower()[:254]
                password = str(data.get("password", ""))
                reward = str(data.get("reward_title", "")).strip()[:80]
                try:
                    required = int(data.get("stamps_required", 5))
                except (ValueError, TypeError):
                    raise ApiError(400, "Damga hedefi geçersiz.")
                if not (name and business and reward and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
                        and len(password) >= 10 and 2 <= required <= 20):
                    raise ApiError(400, "Alanları kontrol edin. Şifre en az 10 karakter olmalı.")
                slug = secrets.token_urlsafe(8).lower().replace("_", "-")
                try:
                    cursor = db.execute("""INSERT INTO merchants(name,email,password_hash,business_name,slug,reward_title,stamps_required,created_at)
                      VALUES(?,?,?,?,?,?,?,?)""", (name, email, password_hash(password), business, slug, reward, required, utcnow()))
                except sqlite3.IntegrityError:
                    raise ApiError(409, "Bu e-posta zaten kayıtlı.")
                return self.start_session(db, cursor.lastrowid)

            if path == "/api/login" and self.command == "POST":
                email = str(data.get("email", "")).strip().lower()
                row = db.execute("SELECT * FROM merchants WHERE email=?", (email,)).fetchone()
                if not row or not password_matches(str(data.get("password", "")), row["password_hash"]):
                    raise ApiError(401, "E-posta veya şifre hatalı.")
                return self.start_session(db, row["id"])

            if path == "/api/logout" and self.command == "POST":
                db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(self.cookie_value("loyalty_session") or ""),))
                return self.respond_committed(db, 200, {"ok": True}, self.cookie_header("loyalty_session", "", 0))

            if path == "/api/me" and self.command == "GET":
                return self.respond(200, {"merchant": public_merchant(self.merchant(db))})

            if path == "/api/merchant/qr" and self.command == "GET":
                merchant = self.merchant(db)
                now = time.time()
                slot = int(now // 60)
                return self.respond(200, {"scan_token": make_scan_token(merchant["id"], slot),
                                          "refresh_in_ms": int(((slot + 1) * 60 - now) * 1000)})

            if path == "/api/dashboard" and self.command == "GET":
                merchant = self.merchant(db)
                metrics = dict(db.execute("""SELECT COUNT(CASE WHEN visits > 0 THEN 1 END) AS customers, COALESCE(SUM(visits),0) AS visits,
                  COALESCE(SUM(rewards_redeemed),0) AS redeemed,
                  COALESCE(SUM(CASE WHEN visits >= 2 THEN 1 ELSE 0 END),0) AS returning_customers
                  FROM cards WHERE merchant_id=?""", (merchant["id"],)).fetchone())
                metrics["returning"] = metrics.pop("returning_customers")
                recent = [dict(r) for r in db.execute("""SELECT v.id, v.approved_at, c.id AS card_id, c.visits
                  FROM visits v JOIN cards c ON c.id=v.card_id
                  WHERE c.merchant_id=? AND v.status='approved' ORDER BY v.id DESC LIMIT 8""", (merchant["id"],))]
                redemptions = [dict(r) for r in db.execute("""SELECT r.id, r.created_at, c.id AS card_id, c.rewards_available
                  FROM redemptions r JOIN cards c ON c.id=r.card_id
                  WHERE c.merchant_id=? AND r.status='pending' ORDER BY r.id DESC""", (merchant["id"],))]
                return self.respond(200, {"merchant": public_merchant(merchant), "metrics": metrics,
                                          "recent": recent, "redemptions": redemptions})

            match = re.fullmatch(r"/api/card/([a-zA-Z0-9_-]+)", path)
            if match and self.command == "GET":
                merchant, card, cookie = self.card(db, match.group(1))
                redeeming = db.execute("SELECT id FROM redemptions WHERE card_id=? AND status='pending'", (card["id"],)).fetchone()
                return self.respond_committed(db, 200, {"merchant": public_merchant(merchant), "card": dict(card),
                                          "redemption_pending": bool(redeeming)}, cookie)

            match = re.fullmatch(r"/api/card/([a-zA-Z0-9_-]+)/(scan|redeem)", path)
            if match and self.command == "POST":
                if match.group(2) == "scan":
                    target = db.execute("SELECT id FROM merchants WHERE slug=?", (match.group(1),)).fetchone()
                    if not target or not valid_scan_token(target["id"], str(data.get("scan_token", ""))):
                        raise ApiError(400, "QR süresi dolmuş. İşletmedeki güncel QR kodunu okut.")
                db.execute("BEGIN IMMEDIATE")
                merchant, card, cookie = self.card(db, match.group(1))
                if match.group(2) == "scan":
                    recent = db.execute("""SELECT approved_at FROM visits WHERE card_id=? AND status='approved'
                      ORDER BY id DESC LIMIT 1""", (card["id"],)).fetchone()
                    if recent and datetime.fromisoformat(recent["approved_at"]) > datetime.now(timezone.utc) - timedelta(hours=1):
                        raise ApiError(429, "Bu kartın damgası zaten işlendi. Yeni damga için bir saat bekle.")
                    stamped_at = utcnow()
                    earned = card["stamps"] + 1 >= merchant["stamps_required"]
                    db.execute("""INSERT INTO visits(card_id,status,created_at,approved_at)
                      VALUES(?,'approved',?,?)""", (card["id"], stamped_at, stamped_at))
                    db.execute("""UPDATE cards SET visits=visits+1, stamps=?, rewards_available=rewards_available+?
                      WHERE id=?""", (0 if earned else card["stamps"] + 1, int(earned), card["id"]))
                    return self.respond_committed(db, 200, {"awarded": True, "earned_reward": earned}, cookie)
                else:
                    if card["rewards_available"] < 1:
                        raise ApiError(409, "Kullanılabilir ödül yok.")
                    if db.execute("SELECT 1 FROM redemptions WHERE card_id=? AND status='pending'", (card["id"],)).fetchone():
                        raise ApiError(409, "Ödül onay bekliyor.")
                    db.execute("INSERT INTO redemptions(card_id,status,created_at) VALUES(?,'pending',?)", (card["id"], utcnow()))
                return self.respond_committed(db, 200, {"ok": True}, cookie)

            match = re.fullmatch(r"/api/redemptions/(\d+)/approve", path)
            if match and self.command == "POST":
                merchant = self.merchant(db)
                db.execute("BEGIN IMMEDIATE")
                item = db.execute(f"""SELECT x.*, c.stamps, c.rewards_available, m.stamps_required
                  FROM redemptions x JOIN cards c ON c.id=x.card_id JOIN merchants m ON m.id=c.merchant_id
                  WHERE x.id=? AND m.id=? AND x.status='pending'""", (int(match.group(1)), merchant["id"])).fetchone()
                if not item:
                    raise ApiError(404, "Bekleyen istek bulunamadı.")
                if item["rewards_available"] < 1:
                    raise ApiError(409, "Ödül artık kullanılamıyor.")
                db.execute("UPDATE redemptions SET status='approved', approved_at=? WHERE id=?", (utcnow(), item["id"]))
                db.execute("""UPDATE cards SET rewards_available=rewards_available-1,
                  rewards_redeemed=rewards_redeemed+1 WHERE id=?""", (item["card_id"],))
                return self.respond_committed(db, 200, {"ok": True})

        raise ApiError(404, "İstek bulunamadı.")

    def start_session(self, db: sqlite3.Connection, merchant_id: int) -> None:
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
        db.execute("INSERT INTO sessions(token_hash,merchant_id,expires_at) VALUES(?,?,?)",
                   (digest(token), merchant_id, expires))
        merchant = db.execute("SELECT * FROM merchants WHERE id=?", (merchant_id,)).fetchone()
        self.respond_committed(db, 200, {"merchant": public_merchant(merchant)},
                     self.cookie_header("loyalty_session", token, SESSION_DAYS * 86400))

    def do_GET(self) -> None:
        self.dispatch()

    def do_POST(self) -> None:
        self.dispatch()

    def dispatch(self) -> None:
        try:
            self.route()
        except ApiError as error:
            self.respond(error.status, {"error": error.message})
        except (ValueError, sqlite3.Error) as error:
            self.log_error("Request failed: %s", error)
            self.respond(500, {"error": "Sunucu hatası."})


def main() -> None:
    init_db()
    if DEMO_MODE:
        seed_demo()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Sadakat v1: http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
