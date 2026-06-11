"""Symbol universes for the screener.

SP100 is a static snapshot of S&P 100 membership (pinned June 2026 —
membership churns a handful of names a year; refresh opportunistically).
Static beats live constituent scraping: deterministic, offline-testable,
and the screener's job is candidate generation, not index tracking.
"""

from __future__ import annotations

SP100: list[str] = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "BRK-B", "C",
    "CAT", "CHTR", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS",
    "CVX", "DE", "DHR", "DIS", "DUK", "EMR", "ETN", "F", "FDX", "GD",
    "GE", "GILD", "GM", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU",
    "ISRG", "JNJ", "JPM", "KO", "LIN", "LLY", "LMT", "LOW", "MA", "MCD",
    "MDLZ", "MDT", "MET", "META", "MMM", "MO", "MRK", "MS", "MSFT", "NEE",
    "NFLX", "NKE", "NOW", "NVDA", "ORCL", "PEP", "PFE", "PG", "PLTR", "PM",
    "PYPL", "QCOM", "RTX", "SBUX", "SCHW", "SO", "SPG", "T", "TGT", "TMO",
    "TMUS", "TSLA", "TXN", "UNH", "UNP", "UPS", "USB", "V", "VZ", "WFC",
    "WMT", "XOM",
]

GROUPS: dict[str, list[str]] = {
    "sp100": SP100,
    "indices": ["^GSPC", "^DJI", "^IXIC", "^FTSE", "^GDAXI", "^N225", "^HSI"],
    "fx": ["EURUSD=X", "USDJPY=X", "GBPUSD=X", "AUDUSD=X", "USDCAD=X"],
    "futures": ["ES=F", "NQ=F", "GC=F", "SI=F", "CL=F", "NG=F"],
    "crypto": ["BTC/USD", "ETH/USD", "SOL/USD", "BNB-USD", "XRP-USD", "DOGE-USD"],
}
