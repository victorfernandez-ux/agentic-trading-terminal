"""Technical-analysis engine: indicator math + composite signal."""

from app.analytics.technical import (
    atr,
    bollinger,
    compute_indicators,
    ema,
    macd,
    rsi,
    sma,
)


def _bars(closes):
    return [{"t": i * 1000, "o": c, "h": c + 1, "l": c - 1, "c": c, "v": 10}
            for i, c in enumerate(closes)]


def test_sma_alignment_and_values():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]


def test_ema_seeds_with_sma_then_smooths():
    out = ema([1.0, 2.0, 3.0, 4.0], 3)
    assert out[0] is None and out[1] is None
    assert out[2] == 2.0  # seed = SMA(1,2,3)
    assert out[3] == 3.0  # 4*0.5 + 2*0.5


def test_rsi_extremes_and_alignment():
    up = [float(i) for i in range(1, 30)]
    out = rsi(up, 14)
    assert out[13] is None and out[14] == 100.0  # all gains
    down = [float(i) for i in range(30, 1, -1)]
    assert rsi(down, 14)[-1] == 0.0  # all losses


def test_macd_shapes_and_uptrend_sign():
    closes = [100 * 1.01 ** i for i in range(60)]
    line, sig, hist = macd(closes)
    assert len(line) == len(sig) == len(hist) == 60
    assert line[-1] is not None and line[-1] > 0  # fast EMA above slow in uptrend


def test_bollinger_constant_series_collapses_to_price():
    closes = [50.0] * 25
    mid, up, lo = bollinger(closes)
    assert mid[-1] == 50.0 and up[-1] == 50.0 and lo[-1] == 50.0


def test_atr_constant_range():
    n = 40
    highs = [101.0] * n
    lows = [99.0] * n
    closes = [100.0] * n
    out = atr(highs, lows, closes, 14)
    assert out[13] is None
    assert abs(out[-1] - 2.0) < 1e-9  # TR is always high-low = 2


def test_compute_indicators_signal_votes_and_payload():
    closes = [100.0] * 30 + [100 * 0.985 ** i for i in range(1, 31)]
    out = compute_indicators(_bars(closes))
    assert out["signal"]["label"] in ("bearish", "neutral")
    factors = {v["factor"] for v in out["signal"]["votes"]}
    assert "trend" in factors and "rsi" in factors
    assert out["latest"]["close"] == closes[-1]
    assert len(out["series"]["sma20"]) == len(closes)


def test_compute_indicators_too_few_bars():
    assert "error" in compute_indicators(_bars([1.0]))
