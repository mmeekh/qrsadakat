"""The map: every business with a pin, plus address search for placing one."""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from urllib.parse import urlencode

from . import config
from .accounts import current_user, customer_of, require_user
from .demo import DEMO_DOMAIN
from .merchants import public_merchant
from .web import ApiError, Request, Router

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
routes = Router()
_lock = threading.Lock()
_last_call = 0.0


def geocode(query: str) -> list[dict]:
    """Address search through Nominatim, kept under its one-request-per-second policy."""
    global _last_call
    url = NOMINATIM_URL + "?" + urlencode({"q": query, "format": "jsonv2", "limit": 5, "accept-language": "tr"})
    request = urllib.request.Request(url, headers={"User-Agent": "cheabby-pilot/1.0 (+https://qrsadakat.duckdns.org)"})
    with _lock:
        wait = 1.1 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                results = json.loads(response.read(262_144))
        except (OSError, ValueError):
            raise ApiError(502, "Adres araması şu an yanıt vermiyor. Konumu haritadan seç.") from None
    return [{"label": str(item["display_name"])[:200], "lat": float(item["lat"]), "lng": float(item["lon"])}
            for item in results if isinstance(item, dict) and {"display_name", "lat", "lon"} <= item.keys()]


@routes.get("/api/places")
def places(req: Request) -> dict:
    customer = customer_of(req, current_user(req))
    hide_demo = "" if config.DEMO_MODE else f" AND m.email NOT LIKE '%{DEMO_DOMAIN}'"
    rows = req.db.execute(f"""SELECT m.*, c.stamps AS my_stamps, c.rewards_available AS my_rewards
      FROM merchants m LEFT JOIN cards c ON c.merchant_id=m.id AND c.customer_id=?
      WHERE m.lat IS NOT NULL AND m.lng IS NOT NULL{hide_demo} ORDER BY m.business_name""",
                          (customer,))
    result = []
    for row in rows:
        place = public_merchant(row)
        place["mine"] = None if row["my_stamps"] is None else {
            "stamps": row["my_stamps"], "rewards_available": row["my_rewards"]}
        result.append(place)
    return {"places": result}


@routes.get("/api/geocode")
def search_address(req: Request) -> dict:
    require_user(req)
    query = " ".join(req.arg("q").split())[:160]
    if len(query) < 3:
        raise ApiError(400, "Adres en az 3 karakter olmalı.")
    return {"results": geocode(query)}
