"""Notification dispatch (roadmap E2) — thin, adapter-based, best-effort.

One interface, N adapters (Telegram today; Discord/Slack are additive).
Notifications are strictly informational: they announce fired alerts and
new PENDING_APPROVAL proposals with a link back into the terminal.
Approval NEVER happens in chat — the approval gate stays in the app.

Failure policy: notify paths are fire-and-forget and swallowed — a dead
bot token must never block the alert evaluator or an order proposal.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("notify")

_TASKS: set[asyncio.Task] = set()  # keep refs so tasks aren't GC'd


async def notify(kind: str, payload: dict) -> None:
    """Send `kind` to every enabled adapter; errors are logged, never raised."""
    from app.notify import telegram

    for adapter in (telegram,):
        try:
            if adapter.enabled():
                await adapter.send(kind, payload)
        except Exception:  # noqa: BLE001 -- notifications are best-effort
            log.warning("notify adapter %s failed for %s",
                        adapter.__name__, kind, exc_info=True)


def notify_bg(kind: str, payload: dict) -> None:
    """Fire-and-forget from sync or async code. Outside an event loop
    (tests, scripts) this is a silent no-op — never a crash."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(notify(kind, payload))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
