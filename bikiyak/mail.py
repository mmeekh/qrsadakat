"""Welcome e-mail: once, to a new customer at their first Google sign-in. bikıyak sends no
other automatic e-mail. Owners are skipped (their business is set up by the operator).

Off until BIKIYAK_WELCOME_MAIL=1: the text and the banner are approved first. Sent through
Resend (RESEND_API_KEY, from /root/secrets/bikiyak-resend.env) on a background thread, so a
slow provider never delays sign-in. sent_mails keeps one row per user and kind: nobody gets
the same mail twice, and failures stay visible there. There is no automatic retry.

    python -m bikiyak.admin welcome-preview > onizleme.html
    python -m bikiyak.admin welcome-test adres@gmail.com "Ayşe Yılmaz"   # sends, records nothing
"""

from __future__ import annotations

import html
import json
import threading
import urllib.error
import urllib.request
from contextlib import closing

from . import config
from .db import connect, utcnow, write

KIND_WELCOME = "welcome"
RESEND_API = "https://api.resend.com/emails"
SENDER = "bikıyak <merhaba@xn--bikyak-r9a.com>"
REPLY_TO = "iletisim@xn--bikyak-r9a.com"
SUBJECT = "bikıyak'a hoş geldin: kartların artık seninle"
PREHEADER = "Kasadaki QR'ı okut, damgan anında kartına işlensin. Kartların Google hesabında güvende."
BANNER = "brand/mail-banner.jpg"
# Brand palette (static/styles.css tokens).
PRIMARY, INK, INK_2, ACCENT, BG, LINE = "#2447F5", "#0B1433", "#525C78", "#FFC933", "#F2F4FA", "#E1E5F0"
STEPS = (
    ("Kasadaki QR'ı okut", "Anlaşmalı işletmede telefonunun kamerasıyla. Uygulama indirmen gerekmez."),
    ("Damgan anında işlensin", "Kartın Google hesabına bağlı; telefon değişse de damgaların kaybolmaz."),
    ("Ödülünü al", "Hedef dolunca kartından \"Ödülümü kullan\"a dokun, kasada göster."),
)
TRUST_TITLE = "E-postanı işletmelerle paylaşmıyoruz"
TRUST = ("Damga aldığın işletme yalnız adını ve soyadının baş harfini (ör. \"Ayşe Y.\") ve ziyaretlerini görür. "
         "E-posta adresin ve fotoğrafın sende kalır.")
FOOTER = "Bu maili bikıyak hesabını açtığın için bir kez aldın. Başka otomatik mail göndermiyoruz."
RUN_INLINE = False  # tests send on the calling thread

_lock = threading.Lock()


def site() -> str:
    return config.PUBLIC_URL or "https://xn--bikyak-r9a.com"


def first_name(name: str) -> str:
    parts = str(name or "").split()
    return parts[0][:40] if parts and "@" not in parts[0] else ""


def render_welcome(name: str = "") -> tuple[str, str, str]:
    """(subject, plain text, HTML). Tables and inline styles only: that is what mail clients keep."""
    first = first_name(name)
    hello = f"Merhaba {first}," if first else "Merhaba,"
    intro = "bikıyak hesabın açıldı. Mahallendeki anlaşmalı işletmelerde damga toplamaya hazırsın."
    cards, places, privacy = f"{site()}/?view=cards", f"{site()}/?view=map", f"{site()}/gizlilik"
    text = (f"{hello}\n\n{intro}\n\nNASIL ÇALIŞIR\n"
            + "\n".join(f"{i}. {title}. {body}" for i, (title, body) in enumerate(STEPS, 1))
            + f"\n\n{TRUST_TITLE.upper()}\n{TRUST}\n\nKartlarım: {cards}\nHarita: {places}\n\n"
            + "Sorun ya da soru olursa bu maile yanıt ver.\n\nbikıyak ekibi\n\n--\n"
            + f"{FOOTER}\nGizlilik: {privacy}\n")

    e = html.escape
    font = "font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    steps = "".join(
        f'<tr><td valign="top" width="38" style="padding:0 12px 16px 0">'
        f'<div style="width:28px;height:28px;border-radius:14px;background:{ACCENT};color:{INK};font-size:14px;'
        f'font-weight:800;text-align:center;line-height:28px">{i}</div></td>'
        f'<td valign="top" style="padding:2px 0 16px 0;font-size:15px;line-height:1.5;color:{INK}">'
        f'<b>{e(title)}.</b> <span style="color:{INK_2}">{e(body)}</span></td></tr>'
        for i, (title, body) in enumerate(STEPS, 1))
    banner_file = config.STATIC_DIR / BANNER
    if banner_file.is_file():
        band = (f'<td style="padding:0;line-height:0;background:{PRIMARY}"><img src="{site()}/{BANNER}" width="560" alt="" '
                f'style="display:block;width:100%;max-width:560px;height:auto;border:0"></td>')
    else:
        # Until the banner exists: the ticket logo on the brand colour, same height, never a broken image.
        band = (f'<td style="padding:34px 32px;background:{PRIMARY};text-align:center">'
                f'<img src="{site()}/brand/logo-ticket.png" width="176" height="56" alt="bikıyak" '
                f'style="display:inline-block;width:176px;height:56px;border:0">'
                f'<div style="{font};font-size:15px;color:#DCE2FF;margin-top:12px">Her ziyarette bi kıyak.</div></td>')
    body = (
        f'<p style="margin:0 0 14px 0;font-size:17px;font-weight:700;color:{INK}">{e(hello)}</p>'
        f'<p style="margin:0 0 22px 0">{e(intro)}</p>'
        f'<p style="margin:0 0 14px 0;font-size:12px;font-weight:700;letter-spacing:1.5px;color:{PRIMARY}">NASIL ÇALIŞIR</p>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 10px 0">'
        f'{steps}</table>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:0 0 26px 0">'
        f'<tr><td style="background:{BG};border-left:3px solid {PRIMARY};padding:16px 18px;border-radius:0 10px 10px 0">'
        f'<div style="font-weight:700;color:{INK};margin:0 0 6px 0">{e(TRUST_TITLE)}</div>'
        f'<div style="font-size:14px;line-height:1.55;color:{INK_2}">{e(TRUST)}</div></td></tr></table>'
        f'<p style="margin:0 0 12px 0"><a href="{cards}" style="display:inline-block;background:{PRIMARY};color:#ffffff;'
        f'text-decoration:none;padding:14px 26px;border-radius:12px;font-weight:700;font-size:15px">Kartlarıma git &rarr;</a></p>'
        f'<p style="margin:0 0 26px 0;font-size:14px"><a href="{places}" style="color:{PRIMARY};font-weight:600">'
        f'Haritada bikıyak geçen işletmeleri gör</a></p>'
        f'<p style="margin:0 0 20px 0">Sorun ya da soru olursa bu maile yanıt ver.</p>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse"><tr>'
        f'<td valign="middle" style="padding:0 12px 0 0"><img src="{site()}/brand/icon-192.png" width="44" height="44" alt="" '
        f'style="display:block;width:44px;height:44px;border-radius:12px"></td>'
        f'<td valign="middle" style="font-size:15px;line-height:1.4;color:{INK}"><b>bikıyak ekibi</b><br>'
        f'<span style="color:{INK_2}">Her ziyarette bi kıyak.</span></td></tr></table>'
    )
    document = (
        f'<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(SUBJECT)}</title></head><body style="margin:0;padding:24px 12px;background:{BG}">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{e(PREHEADER)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">'
        f'<tr><td align="center"><table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:560px;max-width:100%;border-collapse:collapse;background:#ffffff;border:1px solid {LINE};'
        f'border-radius:18px;overflow:hidden"><tr>{band}</tr>'
        f'<tr><td style="padding:32px;{font};font-size:15px;line-height:1.6;color:{INK}">{body}</td></tr>'
        f'<tr><td style="padding:16px 32px 22px 32px;border-top:1px solid {LINE};{font};font-size:12px;line-height:1.5;'
        f'color:{INK_2}">{e(FOOTER)} <a href="{privacy}" style="color:{INK_2}">Gizlilik</a></td></tr>'
        f'</table></td></tr></table></body></html>')
    return SUBJECT, text, document


def deliver(to_address: str, name: str = "") -> str:
    """Sends through Resend; returns Resend's message id or raises."""
    if not config.RESEND_API_KEY:
        raise RuntimeError("Resend anahtarı tanımlı değil")
    subject, text, document = render_welcome(name)
    payload = {"from": SENDER, "to": [to_address], "reply_to": REPLY_TO, "subject": subject, "text": text,
               "html": document, "headers": {"Auto-Submitted": "auto-generated"}}
    request = urllib.request.Request(RESEND_API, data=json.dumps(payload).encode(), method="POST", headers={
        "Authorization": f"Bearer {config.RESEND_API_KEY}", "Content-Type": "application/json",
        "User-Agent": "bikiyak-mail/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return str(json.loads(response.read() or b"{}").get("id", ""))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Resend {error.code}: {error.read(300).decode(errors='replace')}") from None


def send_welcome(user_id: int) -> str:
    """sent | failed | skipped. Never raises: the outcome is written to sent_mails."""
    with _lock:
        with closing(connect()) as db, write(db):
            user = db.execute("SELECT email, name FROM users WHERE id=?", (user_id,)).fetchone()
            if not user or "@" not in user["email"]:
                return "skipped"
            db.execute("""INSERT OR IGNORE INTO sent_mails(user_id,kind,address,status,created_at)
              VALUES(?,?,?,'queued',?)""", (user_id, KIND_WELCOME, user["email"], utcnow()))
            if db.execute("SELECT status FROM sent_mails WHERE user_id=? AND kind=?",
                          (user_id, KIND_WELCOME)).fetchone()["status"] != "queued":
                return "skipped"
        try:
            provider_id, status, error = deliver(user["email"], user["name"]), "sent", ""
        except Exception as problem:  # noqa: BLE001 - every failure is recorded, none escapes
            provider_id, status, error = "", "failed", f"{type(problem).__name__}: {problem}"[:300]
            print(f"welcome mail failed for user {user_id}: {error}", flush=True)
        with closing(connect()) as db:
            db.execute("UPDATE sent_mails SET status=?, error=?, provider_id=?, sent_at=? WHERE user_id=? AND kind=?",
                       (status, error, provider_id, utcnow() if status == "sent" else None, user_id, KIND_WELCOME))
        return status


def schedule_welcome(user_id: int) -> bool:
    if not (config.WELCOME_MAIL and config.RESEND_API_KEY):
        return False
    if RUN_INLINE:
        send_welcome(user_id)
    else:
        threading.Thread(target=send_welcome, args=(user_id,), name="welcome-mail", daemon=True).start()
    return True
