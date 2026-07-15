"""One-time auth tickets for header-less clients (roadmap F1).

EventSource and browser WebSockets can't set an Authorization header, so
SSE/WS auth previously rode the long-lived API_TOKEN in the URL — where
it leaks into server logs, proxies, and browser history. Tickets fix
that: an authenticated client POSTs /auth/ticket, gets a short-lived
single-use ticket, and connects with ?ticket= instead. Redeeming is
destructive, so a logged ticket is worthless seconds later.

In-memory by design: the backend is a single process, and a restart
invalidating in-flight tickets just means one reconnect. ?token= keeps
working for compatibility.
"""

from __future__ import annotations

import time
import uuid

TTL_S = 60.0
_TICKETS: dict[str, float] = {}  # ticket -> expiry (monotonic-ish epoch)
_MAX_OUTSTANDING = 1000  # runaway-mint backstop


def mint() -> str:
    now = time.time()
    for t, exp in list(_TICKETS.items()):  # prune expired on every mint
        if exp < now:
            _TICKETS.pop(t, None)
    if len(_TICKETS) >= _MAX_OUTSTANDING:
        _TICKETS.clear()  # fail-safe: better to drop tickets than grow
    ticket = "tkt_" + uuid.uuid4().hex
    _TICKETS[ticket] = now + TTL_S
    return ticket


def redeem(ticket: str | None) -> bool:
    """Single use: a valid ticket authenticates exactly one request."""
    if not ticket:
        return False
    exp = _TICKETS.pop(ticket, None)
    return exp is not None and exp >= time.time()
