"""Rolling return correlations across symbols (roadmap C3).

One pure function: align bars on common timestamps (drops weekend-only
crypto bars when equities are in the set), compute daily returns, and
return the Pearson correlation matrix over the trailing window. The
watchlist heatmap and the risk agent's concentration signal both read
this — highly-correlated books are one position wearing many tickers.
"""

from __future__ import annotations

import math

_EPS = 1e-12


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a) / n)
    sb = math.sqrt(sum((x - mb) ** 2 for x in b) / n)
    if sa < _EPS or sb < _EPS:
        return None
    return round(cov / (sa * sb), 3)


def compute_correlations(bars_by_symbol: dict[str, list[dict]],
                         window: int = 60) -> dict:
    """Correlation matrix of daily returns over the trailing `window`
    common bars. Symbols with too little overlapping history are dropped
    (reported in `skipped`)."""
    closes: dict[str, dict[int, float]] = {}
    skipped: list[str] = []
    for sym, bars in bars_by_symbol.items():
        by_t = {b["t"]: b["c"] for b in bars if b.get("c") is not None}
        # Pre-filter thin histories: one nearly-empty symbol must not
        # shrink the common-timestamp intersection for everyone else.
        if len(by_t) >= 12:
            closes[sym] = by_t
        else:
            skipped.append(sym)
    common_ts = None
    for by_t in closes.values():
        ts = set(by_t)
        common_ts = ts if common_ts is None else common_ts & ts
    common = sorted(common_ts or [])[-(window + 1):]

    rets: dict[str, list[float]] = {}
    for sym, by_t in closes.items():
        series = [by_t[t] for t in common]
        r = [series[i] / series[i - 1] - 1 for i in range(1, len(series))
             if series[i - 1]]
        if len(r) >= 10:
            rets[sym] = r
        else:
            skipped.append(sym)

    symbols = sorted(rets)
    matrix: list[list[float | None]] = []
    for a in symbols:
        row: list[float | None] = []
        for b in symbols:
            row.append(1.0 if a == b else _pearson(rets[a], rets[b]))
        matrix.append(row)
    # Concentration signal: the average absolute off-diagonal correlation.
    off = [abs(v) for i, row in enumerate(matrix)
           for j, v in enumerate(row) if i != j and v is not None]
    return {
        "symbols": symbols,
        "matrix": matrix,
        "window": window,
        "bars_used": max(len(common) - 1, 0),
        "skipped": skipped,
        "avg_abs_correlation": round(sum(off) / len(off), 3) if off else None,
    }
