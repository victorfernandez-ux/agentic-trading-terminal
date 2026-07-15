"""Telegram adapter (roadmap E2). Plain Bot API over httpx — no SDK.

Off by default: enable by setting TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
in .env. Messages link back into the terminal (PUBLIC_BASE_URL); there
are deliberately no inline buttons — approving happens in the app, only.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

log = logging.getLogger("notify.telegram")


def enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def format_message(kind: str, payload: dict) -> str | None:
    base = settings.public_base_url.rstrip("/")
    if kind == "alert.fired":
        return "🔔 Alert: {msg}\nOpen the terminal: {base}".format(
            msg=payload.get("message", "alert fired"), base=base)
    if kind == "order.pending":
        notional = payload.get("est_notional")
        return ("📋 New proposal: {side} {qty} {sym}{amt} — waiting for YOUR "
                "approval (source: {src}).\nReview in the terminal: {base}"
                .format(side=str(payload.get("side", "?")).upper(),
                        qty=payload.get("qty"), sym=payload.get("symbol"),
                        amt=" (~${:,.0f})".format(notional) if notional else "",
                        src=payload.get("source", "?"), base=base))
    return None


async def send(kind: str, payload: dict) -> bool:
    """POST to the Bot API. Returns False (never raises) on any failure."""
    if not enabled():
        return False
    text = format_message(kind, payload)
    if not text:
        return False
    url = "https://api.telegram.org/bot{t}/sendMessage".format(
        t=settings.telegram_bot_token)
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, json={"chat_id": settings.telegram_chat_id,
                                        "text": text,
                                        "disable_web_page_preview": True})
            r.raise_for_status()
        return True
    except Exception:  # noqa: BLE001 -- best-effort by contract
        log.warning("telegram send failed for %s", kind, exc_info=True)
        return False
