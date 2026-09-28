"""Settings from the environment. Modules read these as `config.NAME` at call time,
so tests can override them without reloading anything."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
DB_PATH = Path(os.environ.get("BIKIYAK_DB", str(ROOT / "pilot.sqlite3")))
HOST = os.environ.get("BIKIYAK_HOST", "127.0.0.1")
PORT = int(os.environ.get("BIKIYAK_PORT", "8088"))
# Google compares redirect_uri byte for byte, so production pins the public origin.
PUBLIC_URL = os.environ.get("BIKIYAK_PUBLIC_URL", "").rstrip("/")
DEMO_MODE = os.environ.get("BIKIYAK_DEMO_MODE", "0") == "1"
# Shows only the showcase demo places (demo.SHOWCASE) on the map, marked "Örnek işletme", without
# the demo login that DEMO_MODE opens.
DEMO_PLACES = os.environ.get("BIKIYAK_DEMO_PLACES", "0") == "1"
# Off: businesses are added by the operator (python -m bikiyak.admin add-merchant ...).
OPEN_SIGNUP = os.environ.get("BIKIYAK_OPEN_SIGNUP", "0") == "1"

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
# The welcome e-mail (mail.py) stays off until its text and banner are approved.
WELCOME_MAIL = os.environ.get("BIKIYAK_WELCOME_MAIL", "0") == "1"

MAX_BODY = 16_384
SESSION_DAYS = 30
OAUTH_STATE_SECONDS = 600
STAMP_COOLDOWN_MINUTES = 60
CATEGORIES = ("Kafe", "Restoran", "Fırın & pastane", "Market", "Berber & kuaför", "Diğer")


def google_enabled() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
