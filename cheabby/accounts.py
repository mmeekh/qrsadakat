"""Google-backed user accounts and their sessions. Every user can collect stamps;
owning a business is an extra role (see merchants.py)."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from . import config
from .db import utcnow
from .web import ApiError, Request, Response, Router

SESSION_COOKIE = "qr_session"
routes = Router()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def upsert_user(db: sqlite3.Connection, sub: str, email: str, name: str, picture: str) -> int:
    db.execute("""INSERT INTO users(google_sub,email,name,picture,created_at,last_login_at) VALUES(?,?,?,?,?,?)
      ON CONFLICT(google_sub) DO UPDATE SET email=excluded.email, name=excluded.name,
      picture=excluded.picture, last_login_at=excluded.last_login_at""",
               (sub, email, name, picture, utcnow(), utcnow()))
    return db.execute("SELECT id FROM users WHERE google_sub=?", (sub,)).fetchone()["id"]


def customer_for_user(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute("SELECT id FROM customers WHERE user_id=?", (user_id,)).fetchone()
    if row:
        return row["id"]
    # token_hash dates from browser-bound cards; a random value keeps the column unique.
    return db.execute("INSERT INTO customers(token_hash,user_id,created_at) VALUES(?,?,?)",
                      (digest(secrets.token_urlsafe(32)), user_id, utcnow())).lastrowid


def start_session(req: Request, response: Response, user_id: int) -> None:
    """Call inside a write transaction."""
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=config.SESSION_DAYS)).isoformat(timespec="seconds")
    req.db.execute("DELETE FROM user_sessions WHERE expires_at<=?", (utcnow(),))
    req.db.execute("INSERT INTO user_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                   (digest(token), user_id, expires))
    req.set_cookie(response, SESSION_COOKIE, token, config.SESSION_DAYS * 86400)


def current_user(req: Request) -> sqlite3.Row | None:
    token = req.cookie(SESSION_COOKIE)
    if not token:
        return None
    return req.db.execute("""SELECT u.* FROM users u JOIN user_sessions s ON s.user_id=u.id
      WHERE s.token_hash=? AND s.expires_at>?""", (digest(token), utcnow())).fetchone()


def require_user(req: Request) -> sqlite3.Row:
    user = current_user(req)
    if not user:
        raise ApiError(401, "Google ile giriş yapman gerekiyor.")
    return user


def public_user(row: sqlite3.Row) -> dict:
    return {"name": row["name"], "email": row["email"], "picture": row["picture"]}


def short_name(name: str) -> str:
    """What a business sees of its customer: "Elif K."."""
    parts = name.split()
    if not parts:
        return "Müşteri"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."


@routes.post("/api/logout")
def logout(req: Request) -> Response:
    req.db.execute("DELETE FROM user_sessions WHERE token_hash=?", (digest(req.cookie(SESSION_COOKIE) or ""),))
    response = Response({"ok": True})
    req.set_cookie(response, SESSION_COOKIE, "", 0)
    return response
