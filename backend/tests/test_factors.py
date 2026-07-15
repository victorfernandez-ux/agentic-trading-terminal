"""Alpha factor pack (roadmap C2): hand-checkable values, PIT safety,
screen integration. Synthetic bars only."""

import pytest

from app.analytics import factors
from app.analytics.screener import SCREENS, _metrics


def _bars(prices, vols=None):
    vols = vols or [1000] * len(prices)
    return [{"t": i * 86_400_000, "o": p, "h": p * 1.01, "l": p * 0.99,
             "c": p, "v": v} for i, (p, v) in enumerate(zip(prices, vols))]


def _steady(n, growth, start=100.0):
    out, px = [], start
    for _ in range(n):
        px *= 1 + growth
        out.append(px)
    return out


def test_mom_12_1_sign_and_short_history():
    rising = _bars(_steady(260, 0.001))
    falling = _bars(_steady(260, -0.001))
    assert factors.mom_12_1(rising) > 0
    assert factors.mom_12_1(falling) < 0
    assert factors.mom_12_1(_bars(_steady(100, 0.001))) is None


def test_mom_12_1_skips_last_month():
    # Flat all year, +20% burst in the last 20 days: 12-1 momentum must
    # ignore the burst (it measures t-252 -> t-21).
    prices = [100.0] * 240 + _steady(20, 0.01)
    assert factors.mom_12_1(_bars(prices)) == pytest.approx(0.0, abs=0.5)


def test_reversal_positive_after_selloff():
    prices = [100.0] * 240 + _steady(21, -0.01)  # 21-day slide
    assert factors.reversal_1m(_bars(prices)) > 15


def test_52w_high_proximity_at_high_is_one():
    prices = _steady(260, 0.001)  # last close IS the 52w high
    assert factors.high_52w_proximity(_bars(prices)) == pytest.approx(1.0)


def test_volatility_ranks_choppy_over_smooth():
    smooth = _bars(_steady(100, 0.0005))
    choppy = _bars([100 * (1 + (0.03 if i % 2 else -0.03)) ** (i % 3)
                    for i in range(100)])
    assert factors.volatility_60d(choppy) > factors.volatility_60d(smooth)


def test_amihud_higher_for_thin_volume():
    prices = [100 * (1 + (0.01 if i % 2 else -0.01)) for i in range(30)]
    thick = _bars(prices, vols=[1_000_000] * 30)
    thin = _bars(prices, vols=[1_000] * 30)
    assert factors.amihud_illiq(thin) > factors.amihud_illiq(thick)


def test_max_ret_catches_lottery_day():
    prices = _steady(30, 0.001)
    prices[-5] = prices[-6] * 1.25  # one +25% lottery day
    prices[-4] = prices[-5] * 0.99
    assert factors.max_ret_21d(_bars(prices)) > 20


def test_alpha101_close_position_in_range():
    # close == high -> ~ (c-o)/(h-l) with c at top of range
    b = [{"t": 0, "o": 100.0, "h": 110.0, "l": 100.0, "c": 110.0, "v": 1}]
    assert factors.alpha101(b) == pytest.approx(1.0, abs=0.01)
    b[0]["c"] = 100.0  # close at the low -> 0
    assert factors.alpha101(b) == pytest.approx(0.0, abs=0.01)


def test_alpha012_volume_confirmed_reversal():
    bars = _bars([100.0, 105.0], vols=[1000, 2000])  # vol up, price up
    assert factors.alpha012(bars) == -5.0  # sign(+1) * -(+5)


def test_pit_safety_appending_future_bars_never_changes_past_values():
    """The factor at bar N uses only bars <= N: recomputing on the prefix
    after 'the future happened' must give the same numbers."""
    full = _bars(_steady(300, 0.001))
    prefix = full[:260]
    before = factors.compute_factors(prefix)
    # mutate the 'future' wildly — prefix values must be unaffected
    for b in full[260:]:
        b["c"] *= 10
    after = factors.compute_factors(full[:260])
    assert before == after


def test_registry_and_screener_integration():
    assert set(factors.compute_factors(_bars(_steady(260, 0.001)))) == set(factors.FACTORS)
    for name in ("factor_momentum", "factor_low_vol", "factor_52w_high",
                 "factor_reversal"):
        assert name in SCREENS
    m = _metrics(_bars(_steady(260, 0.001)))
    assert m["mom_12_1"] is not None  # factors flow into screener rows
