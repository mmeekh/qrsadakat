"""Businesses: the profile an account owner fills in, including the map pin."""

from __future__ import annotations

import secrets
import sqlite3

from . import config
from .accounts import require_user
from .db import utcnow, write
from .web import ApiError, Request, Router

routes = Router()
REWARD_TYPES = ("free", "percent", "amount", "custom")


def public_merchant(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in ("id", "business_name", "slug", "reward_title", "stamps_required", "category",
                                "address", "lat", "lng", "reward_type", "reward_item", "reward_amount")}


def merchant_of(db: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM merchants WHERE user_id=?", (user_id,)).fetchone()


def merchant_by_slug(db: sqlite3.Connection, slug: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM merchants WHERE slug=?", (slug,)).fetchone()
    if not row:
        raise ApiError(404, "İşletme bulunamadı.")
    return row


def require_merchant(req: Request) -> sqlite3.Row:
    row = merchant_of(req.db, require_user(req)["id"])
    if not row:
        raise ApiError(403, "Bu hesaba bağlı bir işletme yok.")
    return row


def clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def reward_title(kind: str, item: str, amount: int, required: int, custom: str) -> str:
    """What customers read on the card and the map."""
    if kind == "free":
        return f"{required} damga topla, {item} bedava"
    if kind == "percent":
        return f"{required} damga topla, %{amount} indirim kazan"
    if kind == "amount":
        return f"{required} damga topla, {amount} ₺ indirim kazan"
    return custom


def read_reward(data: dict) -> dict:
    kind = str(data.get("reward_type") or "custom")
    item, custom = clean(data.get("reward_item"), 40), clean(data.get("reward_title"), 80)
    try:
        amount = int(data.get("reward_amount") or 0)
    except (ValueError, TypeError):
        raise ApiError(400, "İndirim bir sayı olmalı.") from None
    if kind not in REWARD_TYPES:
        raise ApiError(400, "Ödül türü geçersiz.")
    if kind == "free" and len(item) < 2:
        raise ApiError(400, "Bedava verilecek ürünü yaz (ör. 1 kahve).")
    if kind == "percent" and not 5 <= amount <= 100:
        raise ApiError(400, "İndirim oranı %5 ile %100 arasında olmalı.")
    if kind == "amount" and not 1 <= amount <= 10_000:
        raise ApiError(400, "İndirim tutarı 1 ile 10.000 ₺ arasında olmalı.")
    if kind == "custom" and not custom:
        raise ApiError(400, "Ödül metnini yaz.")
    return {"reward_type": kind, "reward_item": item if kind == "free" else "",
            "reward_amount": amount if kind in ("percent", "amount") else 0, "custom": custom}


def read_profile(data: dict) -> dict:
    profile = {"business_name": clean(data.get("business_name"), 80),
               **read_reward(data),
               "category": str(data.get("category", "")),
               "address": clean(data.get("address"), 160)}
    try:
        profile["stamps_required"] = int(data.get("stamps_required", 5))
        profile["lat"], profile["lng"] = float(data.get("lat")), float(data.get("lng"))
    except (ValueError, TypeError):
        raise ApiError(400, "Haritada işletmenin yerini seç.") from None
    if not (profile["business_name"] and profile["category"] in config.CATEGORIES
            and len(profile["address"]) >= 3 and 2 <= profile["stamps_required"] <= 20):
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
            # The stamp goal stays fixed: open cards were counted against it.
            profile["stamps_required"] = existing["stamps_required"]
        profile["reward_title"] = reward_title(profile["reward_type"], profile["reward_item"], profile["reward_amount"],
                                               profile["stamps_required"], profile.pop("custom"))
        if existing:
            db.execute("""UPDATE merchants SET business_name=:business_name, reward_title=:reward_title,
              reward_type=:reward_type, reward_item=:reward_item, reward_amount=:reward_amount,
              category=:category, address=:address, lat=:lat, lng=:lng WHERE id=:id""",
                       {**profile, "id": existing["id"]})
            merchant_id = existing["id"]
        else:
            # merchants.email is UNIQUE from the password era; the account id keeps it unique.
            merchant_id = db.execute("""INSERT INTO merchants(name,email,password_hash,business_name,slug,
              reward_title,stamps_required,created_at,user_id,category,address,lat,lng,
              reward_type,reward_item,reward_amount)
              VALUES(:name,:email,'',:business_name,:slug,:reward_title,:stamps_required,:now,:user_id,
              :category,:address,:lat,:lng,:reward_type,:reward_item,:reward_amount)""", {
                **profile, "name": user["name"], "email": f"{user['email']}#{user['id']}",
                "slug": secrets.token_urlsafe(8).lower().replace("_", "-"), "now": utcnow(),
                "user_id": user["id"]}).lastrowid
        merchant = db.execute("SELECT * FROM merchants WHERE id=?", (merchant_id,)).fetchone()
    return {"merchant": public_merchant(merchant)}
