"""Broker execution adapters (paper -> live).

Safety: this module is reached *only after* a human approves an order
(see app/api/orders.py). The default broker is a paper stub. A live
adapter must refuse to submit unless settings.trading_mode == "live".
"""

from __future__ import annotations

from typing import Protocol

from app.config import settings


class Broker(Protocol):
    async def submit(self, order: dict) -> dict: ...


class PaperBroker:
    """Simulated fills. No real money. Default for all environments."""

    name = "paper"

    async def submit(self, order: dict) -> dict:
        return {
            "broker": self.name,
            "accepted": True,
            "filled_qty": order.get("qty"),
            "status": "filled (simulated)",
            "note": "PaperBroker — no real order was placed",
        }


def get_broker() -> Broker:
    """Return the active broker.

    Phase 1+: return AlpacaBroker() when keys are present and
    trading_mode is explicitly 'live'. Until then, always paper.
    """
    if settings.trading_mode == "live":
        # Phase 5: construct and return a live adapter here, behind
        # additional confirmation. Intentionally not implemented yet.
        raise NotImplementedError(
            "Live trading is not enabled in the scaffold. "
            "Implement a live broker adapter and gating before use."
        )
    return PaperBroker()
