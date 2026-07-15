"""Backtest run cards (roadmap B1): reproducible artifacts per run.

Every saved run writes `<id>.json` (full result: params, data window,
metrics, validation blocks, equity curve) and `<id>.md` (human summary)
under RUNS_DIR (default `.private/runs/`, gitignored). The JSON is the
reproducibility contract: engine version + inputs + seed are all in it.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from app.config import settings

log = logging.getLogger("run_cards")

ENGINE_VERSION = "1"  # bump when run_backtest's semantics change


def _dir() -> Path:
    p = Path(settings.runs_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_run_card(result: dict) -> dict:
    """Persist one backtest result as a run card. Returns {id, path}."""
    card_id = "bt_" + uuid.uuid4().hex[:8]
    card = {
        "id": card_id,
        "created_ts": int(time.time() * 1000),
        "engine_version": ENGINE_VERSION,
        **result,
    }
    d = _dir()
    (d / f"{card_id}.json").write_text(json.dumps(card, default=str, indent=1))
    (d / f"{card_id}.md").write_text(_markdown(card))
    return {"id": card_id, "path": str(d / f"{card_id}.json")}


def _markdown(card: dict) -> str:
    m = card.get("metrics") or {}
    lines = [
        "# Run card {}".format(card["id"]),
        "",
        "- **symbol / strategy**: {} / {} {}".format(
            card.get("symbol"), card.get("strategy"), card.get("params") or ""),
        "- **window**: {} → {} ({} bars, {})".format(
            card.get("start_t"), card.get("end_t"), card.get("bars_count"),
            card.get("timeframe", "1D")),
        "- **engine**: v{} · fee {} bps · initial ${:,.0f}".format(
            card["engine_version"], card.get("fee_bps"),
            card.get("initial_cash") or 0),
        "- **return**: {}% (buy-hold {}%) · trades: {} · win rate: {}%".format(
            card.get("total_return_pct"), card.get("buy_hold_return_pct"),
            card.get("n_trades"), card.get("win_rate_pct")),
        "- **risk**: sharpe {} · max drawdown {}%".format(
            m.get("sharpe"), m.get("max_drawdown_pct")),
    ]
    val = card.get("validation") or {}
    wf = val.get("walk_forward") or {}
    if wf and not wf.get("error"):
        lines.append("- **walk-forward**: {}/{} windows positive · worst {}% · {}".format(
            wf.get("positive_windows"), wf.get("n_windows"),
            wf.get("worst_window_pct"),
            "HOLDS" if wf.get("holds") else
            ("ONE-REGIME" if wf.get("one_regime") else "weak")))
    mc = val.get("monte_carlo") or {}
    if mc and not mc.get("error"):
        r = mc.get("return_pct") or {}
        lines.append("- **bootstrap ({} sims, seed {})**: return P5 {}% / P50 {}% / P95 {}%".format(
            mc.get("n_sims"), mc.get("seed"), r.get("p5"), r.get("p50"), r.get("p95")))
    bench = card.get("benchmark") or {}
    if bench and not bench.get("error"):
        lines.append("- **vs {}**: excess {}% · information ratio {}".format(
            bench.get("benchmark"), bench.get("excess_return_pct"),
            bench.get("information_ratio")))
    return "\n".join(lines) + "\n"


def list_run_cards(limit: int = 50) -> list[dict]:
    """Newest-first index of saved run cards (compact summaries)."""
    cards: list[dict] = []
    files = sorted(_dir().glob("bt_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:limit]:
        try:
            c = json.loads(path.read_text())
            cards.append({k: c.get(k) for k in
                          ("id", "created_ts", "symbol", "strategy", "params",
                           "timeframe", "bars_count", "total_return_pct",
                           "n_trades", "engine_version")})
        except Exception:  # noqa: BLE001 -- one corrupt file never kills the index
            log.warning("unreadable run card %s", path.name)
    return cards


def get_run_card(card_id: str) -> dict | None:
    if not card_id.replace("_", "").isalnum():  # defensive: no path tricks
        return None
    path = _dir() / f"{card_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
