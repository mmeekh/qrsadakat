"""Reward cards ("programs") a business runs. Customer stamp cards belong to one program.
At most five are active at once; a card is archived instead of deleted, so rewards that
customers already earned can still be handed over."""

from __future__ import annotations

import sqlite3

from .db import utcnow, write
from .merchants import clean, require_merchant
from .web import ApiError, Request, Router

REWARD_TYPES = ("free", "percent", "amount", "custom")
MAX_ACTIVE = 5
routes = Router()


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


def public_program(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "merchant_id": row["merchant_id"], "title": row["title"],
            "reward_type": row["reward_type"], "reward_item": row["reward_item"],
            "reward_amount": row["reward_amount"], "stamps_required": row["stamps_required"],
            "archived": row["archived_at"] is not None}


def program_by_id(db: sqlite3.Connection, program_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM programs WHERE id=?", (program_id,)).fetchone()
    if not row:
        raise ApiError(404, "Kart bulunamadı.")
    return row


def own_program(req: Request) -> tuple[sqlite3.Row, sqlite3.Row]:
    merchant = require_merchant(req)
    program = program_by_id(req.db, int(req.params["id"]))
    if program["merchant_id"] != merchant["id"]:
        raise ApiError(404, "Kart bulunamadı.")
    return merchant, program


def active_count(db: sqlite3.Connection, merchant_id: int) -> int:
    return db.execute("SELECT COUNT(*) FROM programs WHERE merchant_id=? AND archived_at IS NULL",
                      (merchant_id,)).fetchone()[0]


def insert_program(db: sqlite3.Connection, merchant_id: int, reward: dict, required: int) -> int:
    title = reward_title(reward["reward_type"], reward["reward_item"], reward["reward_amount"], required, reward["custom"])
    return db.execute("""INSERT INTO programs(merchant_id,title,reward_type,reward_item,reward_amount,
      stamps_required,created_at) VALUES(?,?,?,?,?,?,?)""", (merchant_id, title, reward["reward_type"],
                                                           reward["reward_item"], reward["reward_amount"], required, utcnow())).lastrowid


@routes.get("/api/programs")
def list_programs(req: Request) -> dict:
    merchant = require_merchant(req)
    rows = req.db.execute("""SELECT p.*, COUNT(CASE WHEN c.visits>0 THEN 1 END) AS customers,
      COALESCE(SUM(c.rewards_available),0) AS rewards_waiting
      FROM programs p LEFT JOIN cards c ON c.program_id=p.id WHERE p.merchant_id=?
      GROUP BY p.id ORDER BY p.archived_at IS NOT NULL, p.id""", (merchant["id"],))
    return {"programs": [{**public_program(r), "customers": r["customers"], "rewards_waiting": r["rewards_waiting"]}
                         for r in rows], "max_active": MAX_ACTIVE}


@routes.post("/api/programs")
def create_program(req: Request) -> dict:
    merchant = require_merchant(req)
    reward = read_reward(req.body)
    try:
        required = int(req.body.get("stamps_required", 5))
    except (ValueError, TypeError):
        required = 0
    if not 2 <= required <= 20:
        raise ApiError(400, "Damga hedefi 2 ile 20 arasında olmalı.")
    with write(req.db) as db:
        if active_count(db, merchant["id"]) >= MAX_ACTIVE:
            raise ApiError(409, f"En fazla {MAX_ACTIVE} aktif kart olabilir. Önce birini arşivle.")
        program_id = insert_program(db, merchant["id"], reward, required)
    return {"program": public_program(program_by_id(req.db, program_id))}


@routes.post("/api/programs/{id:int}")
def update_program(req: Request) -> dict:
    _, program = own_program(req)
    reward = read_reward(req.body)
    # The stamp goal stays fixed: open cards were counted against it.
    title = reward_title(reward["reward_type"], reward["reward_item"], reward["reward_amount"],
                         program["stamps_required"], reward["custom"])
    req.db.execute("UPDATE programs SET title=?, reward_type=?, reward_item=?, reward_amount=? WHERE id=?",
                   (title, reward["reward_type"], reward["reward_item"], reward["reward_amount"], program["id"]))
    return {"program": public_program(program_by_id(req.db, program["id"]))}


@routes.post("/api/programs/{id:int}/archive")
def archive_program(req: Request) -> dict:
    merchant, program = own_program(req)
    archive = bool(req.body.get("archived", True))
    with write(req.db) as db:
        if not archive and program["archived_at"] and active_count(db, merchant["id"]) >= MAX_ACTIVE:
            raise ApiError(409, f"En fazla {MAX_ACTIVE} aktif kart olabilir. Önce birini arşivle.")
        db.execute("UPDATE programs SET archived_at=? WHERE id=?", (utcnow() if archive else None, program["id"]))
    return {"program": public_program(program_by_id(req.db, program["id"]))}
