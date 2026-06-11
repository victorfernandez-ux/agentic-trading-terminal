"""Per-symbol news headlines (Yahoo Finance RSS — keyless, survived the 2023
API lockdown; ~20 items per symbol; works for crypto symbols too).

Normalized rows: {title, link, source, published, published_ts}. Failures
degrade to an empty list + error note — headlines are evidence, never a
hard dependency. A tiny in-process TTL cache keeps agent runs and the UI
from hammering the feed.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (compatible; AgenticTradingTerminal/0.1)"}
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL_S = 300.0


def _yahoo_symbol(symbol: str) -> str:
    return symbol.replace("/", "-").upper()


def _parse_rss(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items: list[dict] = []
    for item in root.findall(".//item"):
        pub = (item.findtext("pubDate") or "").strip()
        ts = None
        if pub:
            try:
                ts = int(parsedate_to_datetime(pub).timestamp() * 1000)
            except (TypeError, ValueError):
                ts = None
        link = (item.findtext("link") or "").strip()
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": link,
            "source": (item.findtext("source") or "Yahoo Finance").strip(),
            "published": pub,
            "published_ts": ts,
        })
    items.sort(key=lambda r: r.get("published_ts") or 0, reverse=True)
    return items


async def fetch_news(symbol: str, limit: int = 10) -> list[dict]:
    """Latest headlines for one symbol, newest first (cached ~5 min)."""
    key = _yahoo_symbol(symbol)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL_S:
        return cached[1][:limit]
    url = "https://feeds.finance.yahoo.com/rss/2.0/headline"
    async with httpx.AsyncClient(timeout=12, headers=_UA, follow_redirects=True) as c:
        r = await c.get(url, params={"s": key, "region": "US", "lang": "en-US"})
        r.raise_for_status()
        items = _parse_rss(r.text)
    _CACHE[key] = (now, items)
    return items[:limit]
