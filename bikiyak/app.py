"""Wires the feature modules into one server. A new area (v2 storefront, v3 orders...)
is a new module with its own `routes`, added to FEATURES."""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from . import accounts, auth, config, demo, loyalty, merchants, places, programs
from .db import migrate
from .web import Request, Router, make_handler

FEATURES = (accounts, auth, merchants, programs, loyalty, places, demo)


def build_router() -> Router:
    router = Router()
    for feature in FEATURES:
        router.include(feature.routes)

    @router.get("/api/config")
    def client_config(req: Request) -> dict:
        return {"demo_enabled": config.DEMO_MODE, "google_enabled": config.google_enabled(),
                "categories": config.CATEGORIES}
    return router


def main() -> None:
    migrate()
    if config.DEMO_MODE:
        demo.seed_demo()
    server = ThreadingHTTPServer((config.HOST, config.PORT), make_handler(build_router()))
    print(f"bikıyak: http://{config.HOST}:{config.PORT}", flush=True)
    server.serve_forever()
