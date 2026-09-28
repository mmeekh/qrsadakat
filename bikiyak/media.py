"""Business photos uploaded by the operator (admin set-photo). Stored under MEDIA_DIR by content
hash, so a name never changes meaning and browsers may cache it for good."""

from __future__ import annotations

import hashlib
import re

from . import config

MAX_BYTES = 1_500_000
NAME = re.compile(r"^/media/([0-9a-f]{16}\.(?:jpg|png|webp))$")
MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def suffix_of(data: bytes) -> str | None:
    """The file type from its first bytes, never from the name it was given."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def store(data: bytes) -> str:
    """Saves a photo and returns its public path; ValueError explains a refusal."""
    kind = suffix_of(data)
    if not kind:
        raise ValueError("Fotoğraf JPEG, PNG ya da WebP olmalı.")
    if len(data) > MAX_BYTES:
        raise ValueError(f"Fotoğraf en çok {MAX_BYTES // 1000} KB olabilir; önce küçült (1200 px genişlik yeter).")
    name = f"{hashlib.sha256(data).hexdigest()[:16]}.{kind}"
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (config.MEDIA_DIR / name).write_bytes(data)
    return "/media/" + name


def read(path: str) -> tuple[bytes, str] | None:
    """Body and type for a /media/ path, or None. Only names store() makes are looked up."""
    found = NAME.match(path)
    if not found or not (config.MEDIA_DIR / found[1]).is_file():
        return None
    return (config.MEDIA_DIR / found[1]).read_bytes(), MIME[found[1].rsplit(".", 1)[1]]
