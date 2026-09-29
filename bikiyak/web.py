"""The HTTP layer: routing, requests, responses and static files. Deliberately small;
feature modules only see Router, Request, Response and ApiError."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sqlite3
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from . import config, db as database, media

# Map data (vector tiles, glyphs, sprites, style) comes from OpenFreeMap; MapLibre fetches it,
# also from its worker, which is a same-origin module (worker-src falls back to 'self').
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
       "img-src 'self' data: blob: https://*.googleusercontent.com; "
       "connect-src 'self' https://tiles.openfreemap.org; "
       "worker-src 'self' blob:; child-src 'self' blob:; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8", ".json": "application/json",
        ".css": "text/css; charset=utf-8", ".webp": "image/webp", ".svg": "image/svg+xml",
        ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon", ".woff2": "font/woff2", ".webmanifest": "application/manifest+json"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


class Response:
    def __init__(self, body: object = None, status: int = 200, location: str | None = None):
        self.body, self.status, self.location = body, status, location
        self.cookies: list[str] = []

    @classmethod
    def redirect(cls, location: str) -> Response:
        return cls(status=303, location=location)


class Request:
    def __init__(self, handler: BaseHTTPRequestHandler, params: dict):
        parts = urlsplit(handler.path)
        self.method, self.path, self.params = handler.command, parts.path, params
        self.query = parse_qs(parts.query)
        self.headers = handler.headers
        self.body: dict = {}
        self._handler = handler
        self._db: sqlite3.Connection | None = None

    @property
    def db(self) -> sqlite3.Connection:
        if self._db is None:
            self._db = database.connect()
        return self._db

    def close(self) -> None:
        if self._db is not None:
            self._db.close()

    def arg(self, name: str) -> str:
        return self.query.get(name, [""])[0]

    def cookie(self, name: str) -> str | None:
        try:
            jar = SimpleCookie(self.headers.get("Cookie", ""))
            return jar[name].value if name in jar else None
        except Exception:
            return None

    def set_cookie(self, response: Response, name: str, value: str, max_age: int) -> None:
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        response.cookies.append(f"{name}={value}; HttpOnly; SameSite=Lax; Path=/; Max-Age={max_age}{secure}")

    def origin(self) -> str:
        if config.PUBLIC_URL:
            return config.PUBLIC_URL
        proto = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
        return f"{proto}://{self.headers.get('Host', f'{config.HOST}:{config.PORT}')}"

    def read_json(self) -> None:
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ApiError(415, "JSON bekleniyor.")
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > config.MAX_BODY:
            raise ApiError(413, "İstek çok büyük.")
        try:
            value = json.loads(self._handler.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "Geçersiz JSON.") from None
        if not isinstance(value, dict):
            raise ApiError(400, "Nesne bekleniyor.")
        self.body = value


class Router:
    def __init__(self):
        self.routes: list[tuple[str, re.Pattern, object]] = []

    def route(self, method: str, pattern: str):
        def segment(match: re.Match) -> str:
            kind = r"\d+" if match.group(2) else r"[A-Za-z0-9_-]+"
            return f"(?P<{match.group(1)}>{kind})"
        regex = re.compile("^" + re.sub(r"\{(\w+)(:int)?\}", segment, pattern) + "$")

        def decorate(function):
            self.routes.append((method, regex, function))
            return function
        return decorate

    def get(self, pattern: str):
        return self.route("GET", pattern)

    def post(self, pattern: str):
        return self.route("POST", pattern)

    def include(self, other: Router) -> None:
        self.routes.extend(other.routes)

    def match(self, method: str, path: str):
        for route_method, regex, function in self.routes:
            found = regex.match(path)
            if found and route_method == method:
                return function, found.groupdict()
        return None


def static_files() -> dict[str, tuple[bytes, str, str]]:
    """Loads static/ once at start. Only files that exist there are served; nothing is resolved
    from the URL. Returns {url path: (body, mime type, etag)}.

    Every reference to a stylesheet, script or manifest (in HTML, and module imports in scripts)
    gets ?v=<hash of all static files>, so each deploy changes every URL and no browser or edge
    cache can mix an old module with new ones."""
    paths = sorted(p for p in config.STATIC_DIR.rglob("*") if p.is_file() and p.suffix in MIME)
    raw = {"/" + p.relative_to(config.STATIC_DIR).as_posix(): p.read_bytes() for p in paths}
    version = hashlib.sha256(b"".join(k.encode() + v for k, v in raw.items())).hexdigest()[:10]
    html_ref = re.compile(r'((?:href|src)=")(/[^"?#]+\.(?:css|js|webmanifest))(")')
    js_import = re.compile(r'((?:from|import)\s*")(\.{1,2}/[^"?]+\.js)(")')
    files = {}
    for path, body in raw.items():
        if path.endswith(".html"):
            body = html_ref.sub(lambda m: f"{m[1]}{m[2]}?v={version}{m[3]}", body.decode()).encode()
        elif path.endswith(".js") and not path.startswith("/vendor/"):
            body = js_import.sub(lambda m: f"{m[1]}{m[2]}?v={version}{m[3]}", body.decode()).encode()
        etag = '"' + hashlib.sha256(body).hexdigest()[:20] + '"'
        files[path] = (body, MIME[pathlib.PurePath(path).suffix], etag)
    files["/"] = files["/index.html"]
    # Content pages also answer without the extension: /gizlilik serves gizlilik.html.
    for path in [p for p in files if p.endswith(".html") and p not in ("/index.html", "/404.html")]:
        files[path[:-5]] = files[path]
    return files


def make_handler(router: Router):
    files = static_files()

    class Handler(BaseHTTPRequestHandler):
        server_version = "bikiyak/0.3"

        def log_message(self, format: str, *args) -> None:
            # The OAuth callback carries a one-time code in its query string; keep it out of logs.
            super().log_message(format, *[a.split("?", 1)[0] if isinstance(a, str) else a for a in args])

        def do_GET(self) -> None:
            self.dispatch()

        def do_POST(self) -> None:
            self.dispatch()

        def dispatch(self) -> None:
            path = urlsplit(self.path).path
            if self.command == "GET" and path in files:
                return self.send_static(*files[path])
            photo = media.read(path) if self.command == "GET" and path.startswith("/media/") else None
            if photo:
                return self.send_media(*photo)
            request = None
            try:
                found = router.match(self.command, path)
                if not found and self.command == "GET" and not path.startswith(("/api/", "/auth/")):
                    return self.send_static(*files["/404.html"], status=404)
                if not found:
                    raise ApiError(404, "Bulunamadı.")
                request = Request(self, found[1])
                if self.command == "POST":
                    origin = self.headers.get("Origin")
                    if origin and urlsplit(origin).netloc != self.headers.get("Host", ""):
                        raise ApiError(403, "İstek kaynağı geçersiz.")
                    request.read_json()
                result = found[0](request)
                response = result if isinstance(result, Response) else Response(result)
            except ApiError as error:
                response = Response({"error": error.message}, error.status)
            except (ValueError, sqlite3.Error) as error:
                self.log_error("Request failed: %s", error)
                response = Response({"error": "Sunucu hatası."}, 500)
            finally:
                if request:
                    request.close()
            self.send(response)

        def send(self, response: Response) -> None:
            body = b"" if response.location else json.dumps(response.body, ensure_ascii=False).encode()
            self.send_response(response.status)
            if response.location:
                self.send_header("Location", response.location)
            else:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for cookie in response.cookies:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)

        def send_static(self, body: bytes, mime: str, etag: str, status: int = 200) -> None:
            # Revalidate every time (versioned URLs do the cache busting); the ETag keeps an
            # unchanged file down to a bodiless 304.
            fresh = status == 200 and etag in (self.headers.get("If-None-Match") or "")
            self.send_response(304 if fresh else status)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            if fresh:
                self.end_headers()
                return
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            self.wfile.write(body)

        def send_media(self, body: bytes, mime: str) -> None:
            # Names are content hashes: the same URL always means the same bytes.
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return Handler
