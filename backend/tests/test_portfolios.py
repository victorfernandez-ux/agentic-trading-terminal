"""Portfolio groundwork: default portfolio, order stamping, scoped listing.

Parity: unscoped list_orders/get_positions behave exactly as before; new
orders carry portfolio_id='default'; legacy orders (no portfolio_id) count
as the default when filtering.
"""

import pytest
from fastapi.testclient import TestClient

from app.execution import orders_store, portfolios
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_orders():
    # Reset the order book between tests for deterministic counts.
    from app.core.db import OrderRow, SessionLocal
    with SessionLocal() as s:
        s.query(OrderRow).delete()
        s.commit()
    yield


def _order(**kw):
    base = {"symbol": "AAPL", "side": "buy", "qty": 1, "order_type": "market",
            "est_price": 100.0, "est_notional": 100.0}
    return orders_store.create_pending({**base, **kw})


def test_default_portfolio_exists():
    portfolios.ensure_default()
    ids = {p["id"] for p in portfolios.list_portfolios()}
    assert portfolios.DEFAULT_PORTFOLIO_ID in ids


def test_new_orders_stamped_with_default_portfolio():
    rec = _order()
    assert rec["portfolio_id"] == portfolios.DEFAULT_PORTFOLIO_ID


def test_explicit_portfolio_id_is_preserved():
    rec = _order(portfolio_id="pf_abc")
    assert rec["portfolio_id"] == "pf_abc"


def test_scoped_listing_and_parity():
    _order()                       # default
    _order(portfolio_id="pf_abc")  # other
    all_orders = orders_store.list_orders()
    assert len(all_orders) == 2                     # unscoped = everything (parity)
    assert len(orders_store.list_orders("pf_abc")) == 1
    assert len(orders_store.list_orders(portfolios.DEFAULT_PORTFOLIO_ID)) == 1


def test_legacy_order_without_portfolio_counts_as_default():
    # Simulate a pre-existing order with no portfolio_id in its blob.
    from app.core.db import OrderRow, SessionLocal
    rec = {"id": "ord_legacy", "status": "PENDING_APPROVAL", "symbol": "MSFT",
           "side": "buy", "qty": 1}
    with SessionLocal() as s:
        s.add(OrderRow(id=rec["id"], status=rec["status"], symbol="MSFT", data=rec))
        s.commit()
    scoped = orders_store.list_orders(portfolios.DEFAULT_PORTFOLIO_ID)
    assert any(o["id"] == "ord_legacy" for o in scoped)


def test_create_and_list_portfolio_via_api():
    r = client.post("/portfolios", json={"name": "Swing"})
    assert r.status_code == 200 and r.json()["name"] == "Swing"
    listing = client.get("/portfolios").json()
    assert listing["default"] == portfolios.DEFAULT_PORTFOLIO_ID
    assert any(p["name"] == "Swing" for p in listing["portfolios"])
