"""SQLite access and numbered migrations.

A new feature adds a function to MIGRATIONS; `PRAGMA user_version` records how far a
database has come, so every step runs exactly once and existing data is kept."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone

from . import config


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    # Autocommit; multi-statement writes go through write() below.
    db = sqlite3.connect(config.DB_PATH, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    return db


@contextmanager
def write(db: sqlite3.Connection):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
    except BaseException:
        db.execute("ROLLBACK")
        raise
    db.execute("COMMIT")


def run(db: sqlite3.Connection, script: str) -> None:
    # executescript() would commit mid-migration, so statements run one by one.
    for statement in script.split(";"):
        if statement.strip():
            db.execute(statement)


def add_columns(db: sqlite3.Connection, table: str, columns: tuple[tuple[str, str], ...]) -> None:
    present = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    for name, declaration in columns:
        if name not in present:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def m001_pilot(db: sqlite3.Connection) -> None:
    """The first pilot's schema (IF NOT EXISTS: live pilot databases already have it)."""
    run(db, """
    CREATE TABLE IF NOT EXISTS merchants (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL, business_name TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE, reward_title TEXT NOT NULL,
      stamps_required INTEGER NOT NULL CHECK(stamps_required BETWEEN 2 AND 20),
      created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS customers (
      id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cards (
      id INTEGER PRIMARY KEY, merchant_id INTEGER NOT NULL REFERENCES merchants(id),
      customer_id INTEGER NOT NULL REFERENCES customers(id), stamps INTEGER NOT NULL DEFAULT 0,
      visits INTEGER NOT NULL DEFAULT 0, rewards_available INTEGER NOT NULL DEFAULT 0,
      rewards_redeemed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
      UNIQUE(merchant_id, customer_id));
    CREATE TABLE IF NOT EXISTS visits (
      id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id),
      status TEXT NOT NULL CHECK(status IN ('pending','approved')),
      created_at TEXT NOT NULL, approved_at TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS one_pending_visit ON visits(card_id) WHERE status='pending';
    CREATE TABLE IF NOT EXISTS redemptions (
      id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id),
      status TEXT NOT NULL CHECK(status IN ('pending','approved')),
      created_at TEXT NOT NULL, approved_at TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS one_pending_redemption ON redemptions(card_id) WHERE status='pending'
    """)


def m002_google_accounts_and_places(db: sqlite3.Connection) -> None:
    """Google accounts replace passwords and browser-bound cards; businesses get a map pin."""
    run(db, """
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY, google_sub TEXT NOT NULL UNIQUE, email TEXT NOT NULL,
      name TEXT NOT NULL, picture TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
      last_login_at TEXT);
    CREATE TABLE IF NOT EXISTS user_sessions (
      token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      expires_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS oauth_states (
      state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, verifier TEXT NOT NULL,
      nonce TEXT NOT NULL, intent TEXT NOT NULL, slug TEXT, scan_ok INTEGER NOT NULL DEFAULT 0,
      created_at REAL NOT NULL)
    """)
    add_columns(db, "merchants", (("user_id", "INTEGER REFERENCES users(id)"),
                                  ("category", "TEXT NOT NULL DEFAULT ''"),
                                  ("address", "TEXT NOT NULL DEFAULT ''"),
                                  ("lat", "REAL"), ("lng", "REAL")))
    add_columns(db, "customers", (("user_id", "INTEGER REFERENCES users(id)"),))
    run(db, """
    CREATE UNIQUE INDEX IF NOT EXISTS merchant_owner ON merchants(user_id) WHERE user_id IS NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS customer_user ON customers(user_id) WHERE user_id IS NOT NULL
    """)


def m003_reward_types(db: sqlite3.Connection) -> None:
    """Businesses pick what the reward is: a free item, a percent or amount discount, or own text.
    Existing businesses keep their text as 'custom'."""
    add_columns(db, "merchants", (("reward_type", "TEXT NOT NULL DEFAULT 'custom'"),
                                  ("reward_item", "TEXT NOT NULL DEFAULT ''"),
                                  ("reward_amount", "INTEGER NOT NULL DEFAULT 0")))


def m004_reward_cards(db: sqlite3.Connection) -> None:
    """A business can run several reward cards ("programs"); customer cards belong to one.
    Each business's current reward becomes its first card, and customer cards move onto it
    with their stamps, visits and rewards. The reward columns on merchants are kept unused."""
    run(db, """
    CREATE TABLE programs (
      id INTEGER PRIMARY KEY, merchant_id INTEGER NOT NULL REFERENCES merchants(id),
      title TEXT NOT NULL, reward_type TEXT NOT NULL, reward_item TEXT NOT NULL DEFAULT '',
      reward_amount INTEGER NOT NULL DEFAULT 0,
      stamps_required INTEGER NOT NULL CHECK(stamps_required BETWEEN 2 AND 20),
      archived_at TEXT, created_at TEXT NOT NULL);
    CREATE INDEX programs_merchant ON programs(merchant_id);
    INSERT INTO programs(merchant_id,title,reward_type,reward_item,reward_amount,stamps_required,created_at)
      SELECT id, reward_title, reward_type, reward_item, reward_amount, stamps_required, created_at
      FROM merchants WHERE reward_title<>'';
    CREATE TABLE cards_new (
      id INTEGER PRIMARY KEY, program_id INTEGER NOT NULL REFERENCES programs(id),
      merchant_id INTEGER NOT NULL REFERENCES merchants(id),
      customer_id INTEGER NOT NULL REFERENCES customers(id), stamps INTEGER NOT NULL DEFAULT 0,
      visits INTEGER NOT NULL DEFAULT 0, rewards_available INTEGER NOT NULL DEFAULT 0,
      rewards_redeemed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
      UNIQUE(program_id, customer_id));
    INSERT INTO cards_new(id,program_id,merchant_id,customer_id,stamps,visits,rewards_available,rewards_redeemed,created_at)
      SELECT c.id, p.id, c.merchant_id, c.customer_id, c.stamps, c.visits, c.rewards_available,
             c.rewards_redeemed, c.created_at
      FROM cards c JOIN programs p ON p.merchant_id=c.merchant_id;
    DROP TABLE cards;
    ALTER TABLE cards_new RENAME TO cards;
    CREATE INDEX cards_merchant ON cards(merchant_id);
    CREATE INDEX cards_customer ON cards(customer_id)
    """)
    add_columns(db, "oauth_states", (("program_id", "INTEGER"),))


def m005_merchant_invites(db: sqlite3.Connection) -> None:
    """Businesses open by invitation (27 Eyl 2026). Superseded the same day by the operator
    adding businesses directly (admin add-merchant); the table is kept but no longer read."""
    run(db, """CREATE TABLE merchant_invites (
      email TEXT PRIMARY KEY, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""")


def m006_sent_mails(db: sqlite3.Connection) -> None:
    """One row per user and mail kind (only 'welcome' so far): nobody gets the same mail twice."""
    run(db, """CREATE TABLE sent_mails (
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
      address TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('queued','sent','failed')),
      error TEXT NOT NULL DEFAULT '', provider_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
      sent_at TEXT, UNIQUE(user_id, kind))""")


MIGRATIONS = (m001_pilot, m002_google_accounts_and_places, m003_reward_types, m004_reward_cards,
              m005_merchant_invites, m006_sent_mails)


def migrate() -> None:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as db:
        db.execute("PRAGMA journal_mode=WAL")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        # Rebuilding a referenced table needs foreign keys off (only possible outside a
        # transaction); integrity is checked before the step commits.
        db.execute("PRAGMA foreign_keys=OFF")
        for number, step in enumerate(MIGRATIONS[version:], start=version + 1):
            with write(db):
                step(db)
                broken = db.execute("PRAGMA foreign_key_check").fetchall()
                if broken:
                    raise RuntimeError(f"migration {number} broke foreign keys: {[tuple(r) for r in broken[:5]]}")
                db.execute(f"PRAGMA user_version={number}")
