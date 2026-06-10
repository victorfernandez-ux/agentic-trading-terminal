"""Technical-analysis engine: classic indicators + a composite signal.

Pure functions over OHLCV bars (the normalized shape from app/data/providers).
All series are returned ALIGNED to the input bars: index i of any indicator
series corresponds to bars[i]; positions with insufficient history are None.

No external TA library — implementations follow the standard definitions
(Wilder smoothing for RSI/ATR, EMA seeded with SMA, MACD 12/26/9).
"""

from __future__ import annotations

import math


def sma(values: list[float], period: int) -> list[float | None]:
    """Simple moving average, aligned (None until `period` values exist)."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(values)
    rolling = 0.0
    for i, v in enumerate(values):
        rolling += v
        if i >= period:
            rolling -= values[i - period]
        if i >= period - 1:
            out[i] = rolling / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    """Exponential moving average seeded with the SMA of the first `period`."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1)
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index with Wilder smoothing. 0..100, aligned."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain, avg_loss = gains / period, losses / period

    def _rsi(g: float, l_: float) -> float:
        if l_ == 0:
            return 100.0
        rs = g / l_
        return 100.0 - 100.0 / (1.0 + rs)

    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """MACD line, signal line, histogram — all aligned to `closes`."""
    ema_fast, ema_slow = ema(closes, fast), ema(closes, slow)
    line: list[float | None] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    # Signal = EMA(signal) over the non-None segment of the MACD line.
    start = next((i for i, v in enumerate(line) if v is not None), None)
    sig: list[float | None] = [None] * len(closes)
    if start is not None:
        seg = [v for v in line[start:] if v is not None]
        seg_sig = ema(seg, signal)
        for j, v in enumerate(seg_sig):
            sig[start + j] = v
    hist: list[float | None] = [
        (m - s) if (m is not None and s is not None) else None for m, s in zip(line, sig)
    ]
    return line, sig, hist


def bollinger(
    closes: list[float], period: int = 20, num_std: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Bollinger bands: (middle, upper, lower), population std, aligned."""
    mid = sma(closes, period)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        m = mid[i]
        if m is None:
            continue
        var = sum((c - m) ** 2 for c in window) / period
        sd = math.sqrt(var)
        upper[i] = m + num_std * sd
        lower[i] = m - num_std * sd
    return mid, upper, lower


def atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[float | None]:
    """Average True Range (Wilder), aligned."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out
    trs: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    prev = sum(trs[:period]) / period
    out[period] = prev
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i - 1]) / period
        out[i] = prev
    return out


# ── Composite signal ────────────────────────────────────────────────────


def _last(series: list[float | None]) -> float | None:
    for v in reversed(series):
        if v is not None:
            return v
    return None


def compute_indicators(bars: list[dict]) -> dict:
    """Full indicator snapshot + naive multi-factor signal for one symbol.

    The composite signal is a transparent vote count (each factor explains
    itself) — input for humans and agents, never an order trigger by itself.
    """
    closes = [b["c"] for b in bars]
    highs = [b.get("h", b["c"]) for b in bars]
    lows = [b.get("l", b["c"]) for b in bars]
    if len(closes) < 2:
        return {"bars_count": len(closes), "error": "not enough bars"}

    sma20, sma50 = sma(closes, 20), sma(closes, 50)
    rsi14 = rsi(closes, 14)
    macd_line, macd_sig, macd_hist = macd(closes)
    bb_mid, bb_up, bb_lo = bollinger(closes)
    atr14 = atr(highs, lows, closes, 14)

    price = closes[-1]
    votes: list[dict] = []

    def vote(name: str, direction: int, detail: str) -> None:
        votes.append({"factor": name, "vote": direction, "detail": detail})

    s20, s50 = sma20[-1], sma50[-1]
    if s20 is not None and s50 is not None:
        if s20 > s50:
            vote("trend", +1, f"SMA20 {s20:.2f} above SMA50 {s50:.2f} (uptrend)")
        elif s20 < s50:
            vote("trend", -1, f"SMA20 {s20:.2f} below SMA50 {s50:.2f} (downtrend)")
    if s20 is not None:
        vote("price_vs_sma20", +1 if price >= s20 else -1,
             f"price {price:.2f} {'above' if price >= s20 else 'below'} SMA20")
    r = rsi14[-1]
    if r is not None:
        if r < 30:
            vote("rsi", +1, f"RSI14 {r:.1f} oversold (<30)")
        elif r > 70:
            vote("rsi", -1, f"RSI14 {r:.1f} overbought (>70)")
        else:
            vote("rsi", 0, f"RSI14 {r:.1f} neutral")
    h = macd_hist[-1]
    if h is not None:
        vote("macd", +1 if h > 0 else (-1 if h < 0 else 0),
             f"MACD histogram {h:+.4f}")
    if bb_up[-1] is not None and bb_lo[-1] is not None:
        if price > bb_up[-1]:
            vote("bollinger", -1, "price above upper band (stretched)")
        elif price < bb_lo[-1]:
            vote("bollinger", +1, "price below lower band (washed out)")
        else:
            vote("bollinger", 0, "price inside bands")

    score = sum(v["vote"] for v in votes)
    scorable = sum(1 for v in votes if v["vote"] != 0) or 1
    label = "bullish" if score >= 2 else ("bearish" if score <= -2 else "neutral")

    return {
        "bars_count": len(closes),
        "latest": {
            "close": price,
            "sma20": s20, "sma50": s50,
            "rsi14": r,
            "macd": macd_line[-1], "macd_signal": macd_sig[-1], "macd_hist": h,
            "bb_mid": bb_mid[-1], "bb_upper": bb_up[-1], "bb_lower": bb_lo[-1],
            "atr14": atr14[-1] if atr14 else None,
        },
        "series": {
            "t": [b["t"] for b in bars],
            "sma20": sma20, "sma50": sma50, "rsi14": rsi14,
            "macd_hist": macd_hist, "bb_upper": bb_up, "bb_lower": bb_lo,
        },
        "signal": {"score": score, "of": scorable, "label": label, "votes": votes},
    }
