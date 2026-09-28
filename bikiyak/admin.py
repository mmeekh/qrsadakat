"""Operator commands, run inside the app container. Businesses are added here, not by
self-service sign-up; everyone who signs in on the site starts as a customer.

    python -m bikiyak.admin add-merchant isletme@gmail.com "Nora Café" Kafe "Moda Cd. 12, Kadıköy/İstanbul"
    python -m bikiyak.admin add-merchant isletme@gmail.com "Nora Café" Kafe "Moda, Kadıköy" 40.9837 29.0268
    python -m bikiyak.admin add-merchant isletme@gmail.com     (bilgileri sahibi ilk girişte kendisi kurar)
    python -m bikiyak.admin set-photo isletme@gmail.com /tmp/vitrin.jpg   (JPEG/PNG/WebP, ≤1,5 MB)
    python -m bikiyak.admin merchants
    python -m bikiyak.admin welcome-preview > onizleme.html
    python -m bikiyak.admin welcome-test adres@gmail.com "Ayşe Yılmaz"   (sends; records nothing)

Without coordinates the address is looked up on OpenStreetMap. The owner signs in with Google
using that e-mail and lands on the business side; the pin can be fixed later in the profile."""

from __future__ import annotations

import re
import secrets
import sys
from contextlib import closing
from pathlib import Path

from . import config
from .db import connect, migrate, utcnow, write
from .web import ApiError


def add_merchant(args: list[str]) -> int:
    if len(args) not in (1, 4, 6):
        print("Kullanım: add-merchant E-POSTA [\"İşletme adı\" KATEGORİ \"Adres\" [ENLEM BOYLAM]]", file=sys.stderr)
        return 2
    email_only = len(args) == 1
    if email_only:
        # E-mail only: the owner enters name, category, address and pin at the first sign-in.
        args = args + ["", "", ""]
    email, business, category, address = args[0].strip().lower(), " ".join(args[1].split()), args[2], " ".join(args[3].split())
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        print(f"Geçersiz e-posta: {args[0]}", file=sys.stderr)
        return 2
    lat = lng = None
    if not email_only and (not business or category not in config.CATEGORIES):
        print(f"Ad boş olamaz; kategori şunlardan biri olmalı: {', '.join(config.CATEGORIES)}", file=sys.stderr)
        return 2
    if len(args) == 6:
        lat, lng = float(args[4]), float(args[5])
    elif not email_only:
        from .places import geocode
        try:
            found = geocode(address)
        except ApiError as error:
            print(error.message, file=sys.stderr)
            return 1
        if not found:
            print("Adres haritada bulunamadı; enlem ve boylamı elle ver.", file=sys.stderr)
            return 1
        lat, lng = found[0]["lat"], found[0]["lng"]
        print(f"Konum: {found[0]['label']} ({lat:.5f}, {lng:.5f})")
    with closing(connect()) as db, write(db):
        if db.execute("SELECT 1 FROM merchants WHERE lower(email)=?", (email,)).fetchone():
            print(f"Bu e-postayla zaten bir işletme var: {email}", file=sys.stderr)
            return 1
        user = db.execute("SELECT id FROM users WHERE lower(email)=?", (email,)).fetchone()
        if user and db.execute("SELECT 1 FROM merchants WHERE user_id=?", (user["id"],)).fetchone():
            print("Bu hesabın zaten bir işletmesi var.", file=sys.stderr)
            return 1
        # user_id stays empty until the owner's first Google sign-in (auth.sign_in links by e-mail).
        db.execute("""INSERT INTO merchants(name,email,password_hash,business_name,slug,reward_title,stamps_required,
          created_at,user_id,category,address,lat,lng) VALUES(?,?,'',?,?,'',5,?,?,?,?,?,?)""",
                   (business, email, business, secrets.token_urlsafe(8).lower().replace("_", "-"), utcnow(),
                    user["id"] if user else None, category, address, lat, lng))
    linked = "hesabına hemen bağlandı" if user else "Google ile ilk girişte bağlanacak"
    if not email_only:
        print(f"İşletme eklendi: {business} ({category}) → {email}, {linked}. İlk kartını Kartlarım'dan açar.")
    else:
        print(f"İşletme eklendi: {email}, {linked}. Girişte ad, kategori ve konumu kendisi kurar; o zamana kadar haritada görünmez.")
    return 0


def set_photo(args: list[str]) -> int:
    if len(args) != 2:
        print("Kullanım: set-photo E-POSTA DOSYA", file=sys.stderr)
        return 2
    from .media import store
    email = args[0].strip().lower()
    with closing(connect()) as db, write(db):
        if not db.execute("SELECT 1 FROM merchants WHERE lower(email)=?", (email,)).fetchone():
            print(f"Bu e-postayla işletme yok: {args[0]}", file=sys.stderr)
            return 1
        try:
            photo = store(Path(args[1]).read_bytes())
        except (OSError, ValueError) as error:
            print(error, file=sys.stderr)
            return 1
        db.execute("UPDATE merchants SET photo=? WHERE lower(email)=?", (photo, email))
    print(f"Fotoğraf kondu: {photo}")
    return 0


def list_merchants() -> int:
    with closing(connect()) as db:
        rows = db.execute("""SELECT m.email, m.business_name, m.category, m.user_id IS NOT NULL AS linked,
          (SELECT COUNT(*) FROM programs p WHERE p.merchant_id=m.id AND p.archived_at IS NULL) AS cards
          FROM merchants m WHERE m.email NOT LIKE '%@mahalle.invalid' ORDER BY m.id""").fetchall()
    for row in rows:
        state = "giriş yaptı" if row["linked"] else "henüz girmedi"
        name = row["business_name"] or "(kurulum bekliyor)"
        print(f"{row['email']}\t{name}\t{row['category']}\t{state}\t{row['cards']} aktif kart")
    print(f"{len(rows)} işletme")
    return 0


def main(argv: list[str]) -> int:
    migrate()
    command, args = (argv[0], argv[1:]) if argv else ("", [])
    if command == "add-merchant":
        return add_merchant(args)
    if command == "set-photo":
        return set_photo(args)
    if command == "merchants":
        return list_merchants()
    if command == "welcome-preview":
        from .mail import render_welcome
        print(render_welcome(args[0] if args else "Ayşe Yılmaz")[2])
        return 0
    if command == "welcome-test" and args:
        from .mail import deliver
        print("Resend id:", deliver(args[0], args[1] if len(args) > 1 else ""))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
