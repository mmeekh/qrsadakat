"""Businesses: the profile an account owner fills in, including the map pin.
Rewards live on the business's cards (programs.py)."""

from __future__ import annotations

import secrets
import sqlite3

from . import config
from .accounts import require_user
from .db import utcnow, write
from .web import ApiError, Request, Router

routes = Router()


def public_merchant(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in ("id", "business_name", "slug", "category", "address", "lat", "lng", "photo")}


def merchant_of(db: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM merchants WHERE user_id=?", (user_id,)).fetchone()


def merchant_by_id(db: sqlite3.Connection, merchant_id: int) -> sqlite3.Row:
    return db.execute("SELECT * FROM merchants WHERE id=?", (merchant_id,)).fetchone()


def require_merchant(req: Request) -> sqlite3.Row:
    row = merchant_of(req.db, require_user(req)["id"])
    if not row:
        raise ApiError(403, "Bu hesaba bağlı bir işletme yok.")
    return row


def may_open_business(db: sqlite3.Connection, user: sqlite3.Row) -> bool:
    """Businesses are added by the operator (python -m bikiyak.admin add-merchant); the site
    itself only lets an existing owner edit, unless BIKIYAK_OPEN_SIGNUP is on."""
    return config.OPEN_SIGNUP or merchant_of(db, user["id"]) is not None


def clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def read_profile(data: dict) -> dict:
    profile = {"business_name": clean(data.get("business_name"), 80),
               "category": str(data.get("category", "")),
               "address": clean(data.get("address"), 160)}
    try:
        profile["lat"], profile["lng"] = float(data.get("lat")), float(data.get("lng"))
    except (ValueError, TypeError):
        raise ApiError(400, "Haritada işletmenin yerini seç.") from None
    if not (profile["business_name"] and profile["category"] in config.CATEGORIES and len(profile["address"]) >= 3):
        raise ApiError(400, "Alanları kontrol et.")
    if not (-90 <= profile["lat"] <= 90 and -180 <= profile["lng"] <= 180) \
            or (profile["lat"] == 0 and profile["lng"] == 0):
        raise ApiError(400, "Haritada işletmenin yerini seç.")
    return profile


@routes.post("/api/merchant")
def save_profile(req: Request) -> dict:
    user = require_user(req)
    profile = read_profile(req.body)
    with write(req.db) as db:
        existing = merchant_of(db, user["id"])
        if existing:
            db.execute("""UPDATE merchants SET business_name=:business_name, category=:category,
              address=:address, lat=:lat, lng=:lng WHERE id=:id""", {**profile, "id": existing["id"]})
            merchant_id = existing["id"]
        else:
            if not may_open_business(db, user):
                raise ApiError(403, f"Bu Google hesabı ({user['email']}) henüz işletme olarak eklenmedi.")
            # Password-era columns: email must stay UNIQUE (the account id keeps it so), and the
            # unused reward_title/stamps_required get neutral values; rewards are programs now.
            merchant_id = db.execute("""INSERT INTO merchants(name,email,password_hash,business_name,slug,
              reward_title,stamps_required,created_at,user_id,category,address,lat,lng)
              VALUES(:name,:email,'',:business_name,:slug,'',5,:now,:user_id,:category,:address,:lat,:lng)""", {
                **profile, "name": user["name"], "email": f"{user['email']}#{user['id']}",
                "slug": secrets.token_urlsafe(8).lower().replace("_", "-"), "now": utcnow(),
                "user_id": user["id"]}).lastrowid
        merchant = db.execute("SELECT * FROM merchants WHERE id=?", (merchant_id,)).fetchone()
    return {"merchant": public_merchant(merchant)}
