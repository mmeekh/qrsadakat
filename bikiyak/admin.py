"""Operator commands, run inside the app container:

    python -m bikiyak.admin invite isletme@example.com "Nora Café"
    python -m bikiyak.admin invites
    python -m bikiyak.admin uninvite isletme@example.com

An invited e-mail can open a business after signing in with Google."""

from __future__ import annotations

import re
import sys
from contextlib import closing

from .db import connect, migrate, utcnow


def main(argv: list[str]) -> int:
    migrate()
    command, args = (argv[0], argv[1:]) if argv else ("", [])
    with closing(connect()) as db:
        if command == "invite" and args:
            email = args[0].strip().lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                print(f"Geçersiz e-posta: {args[0]}", file=sys.stderr)
                return 2
            note = " ".join(args[1:])[:120]
            db.execute("""INSERT INTO merchant_invites(email,note,created_at) VALUES(?,?,?)
              ON CONFLICT(email) DO UPDATE SET note=excluded.note""", (email, note, utcnow()))
            print(f"Davet eklendi: {email}{' (' + note + ')' if note else ''}")
            return 0
        if command == "uninvite" and args:
            removed = db.execute("DELETE FROM merchant_invites WHERE email=?", (args[0].strip().lower(),)).rowcount
            print("Davet silindi." if removed else "Böyle bir davet yok.")
            return 0
        if command == "invites":
            rows = db.execute("""SELECT i.email, i.note, i.created_at,
              EXISTS(SELECT 1 FROM users u JOIN merchants m ON m.user_id=u.id WHERE u.email=i.email) AS opened
              FROM merchant_invites i ORDER BY i.created_at""").fetchall()
            for row in rows:
                state = "işletmesini açtı" if row["opened"] else "henüz açmadı"
                print(f"{row['email']}\t{row['note']}\t{row['created_at'][:10]}\t{state}")
            print(f"{len(rows)} davet")
            return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
