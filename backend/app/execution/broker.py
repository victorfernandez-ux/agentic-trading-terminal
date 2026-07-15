"""Broker execution adapters (paper -> live).

Safety: this module is reached *only after* a human approves an order
(see app/api/orders.py). The default broker is a paper stub. A live
adapter must refuse to submit unless settings.trading_mode == "live".

Roadmap F3 rails (Vibe-Trading containment patterns, adopted without the
autonomous trading they contain there):
    * KILL SWITCH — if the file at settings.kill_switch_file exists, every
      submission raises TradingHalted (claim released, order back to
      PENDING_APPROVAL). Cheap now, load-bearing if live ever ships:
      `touch .private/KILL_SWITCH` halts trading with no deploy.
    * STRUCTURAL paper discriminator — get_broker() verifies the adapter
      *itself* declares is_paper, instead of trusting the config flag
      alone; a mismatch fails closed. A future live adapter must prove
      paper-ness structurally (sandbox host, demo account id, ...).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.config import settings


class Broker(Protocol):
    is_paper: bool
    async def submit(self, order: dict) -> dict: ...


class TradingHalted(RuntimeError):
    """Kill switch engaged — no submission may proceed."""


def kill_switch_engaged() -> bool:
    return Path(settings.kill_switch_file).exists()


class PaperBroker:
    """Simulated fills. No real money. Default for all environments."""

    name = "paper"
    is_paper = True  # structural discriminator, asserted by get_broker()

    async def submit(self, order: dict) -> dict:
        if kill_switch_engaged():
            from app.core.audit import audit_log
            audit_log("trading.halted", {"order_id": order.get("id"),
                                         "symbol": order.get("symbol"),
                                         "kill_switch": settings.kill_switch_file})
            raise TradingHalted(
                "kill switch engaged ({}) — remove the file to resume"
                .format(settings.kill_switch_file))
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
    broker = PaperBroker()
    if not getattr(broker, "is_paper", False):  # fail closed, never open
        raise RuntimeError(
            "broker failed the structural paper check — refusing to trade")
    return broker
