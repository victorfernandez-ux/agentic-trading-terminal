"""Analytics suite — capabilities inspired by FinceptTerminal's module set.

Five capabilities, implemented from scratch (no AGPL code reuse):
    technical.py  -> indicator engine (SMA/EMA/RSI/MACD/Bollinger/ATR + signals)
    risk.py       -> quantstats-style risk & performance metrics
    backtest.py   -> strategy backtesting engine (no-lookahead, fee-aware)
    valuation.py  -> DCF valuation with sensitivity grid
    personas.py   -> legendary-investor persona scoring agents

All pure Python over the existing dependency set; deterministic and
offline-testable. Exposed via /analytics endpoints and the agent tool
registry (app/agents/tools.py).
"""
