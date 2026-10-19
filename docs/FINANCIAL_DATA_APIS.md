# Free financial data APIs — research (July 2026)

Goal: reduce reliance on unofficial Yahoo endpoints (chart/spark/RSS/crumb), which
throttle by traffic pattern and can break without notice, using only **free** tiers.
Findings below are ranked by fit for this terminal (watchlist quotes, OHLCV bars,
news/sentiment evidence for agents, fundamentals for valuation, options chains).

## Where we stand today

| Need | Current source | Risk |
|---|---|---|
| Quotes/bars (equity+crypto) | Yahoo v8 chart/spark (keyless, unofficial) | throttling/bans, breaking changes |
| Equity daily fallback | Stooq CSV (keyless) | daily-only |
| Crypto fallback | CCXT → Coinbase/Kraken/Bitstamp public | fine (official public APIs) |
| News | Yahoo RSS | single source, unofficial |
| Fundamentals/options | Yahoo v7/v10 cookie+crumb | most fragile Yahoo surface |
| Keyed extras | Alpaca, Polygon providers exist but keys unset | unused capacity |

## Recommended free additions (ranked)

### 1. Alpaca free data plan — already integrated, just add keys
Free plan: real-time IEX feed, **200 req/min**, WebSocket streaming, ~7 years of
historical bars, no credit card. `AlpacaProvider` already exists in
`providers.py`; setting `alpaca_api_key`/`alpaca_api_secret` immediately gives a
keyed, officially-supported equity source in the fallback chain. Highest
value-for-effort of anything on this list. Free plan also includes the
indicative options feed.

### 2. Finnhub free tier — quotes, company news, basic fundamentals
**60 calls/min**, real-time US quotes, per-company news, basic fundamentals, SEC
filings, WebSocket for up to 50 symbols. Best free source for **company news**
(structured JSON, better than scraping RSS) and a second real-time quote source.
Caveats: stock **candles/OHLC are not on the free tier** (removed in 2023 — quote
+ news + fundamentals only), and the free tier is licensed for personal use.

### 3. SEC EDGAR + FRED — official, keyless/free-key fundamentals & macro
- `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` — all XBRL company
  facts as JSON, **no key**, 10 req/s max, custom User-Agent required. Ticker→CIK
  map at `https://www.sec.gov/files/company_tickers.json`. This should become the
  primary source for the valuation module instead of Yahoo v10 fundamentals.
- FRED API — free key, macro series (rates, CPI, yield curves) for the risk agent.

### 4. Twelve Data — free intraday bars across stocks/forex/crypto
**800 calls/day, 8/min.** Only free source here with proper intraday OHLCV
endpoints across asset classes; data is delayed on the free tier. Good bar-chain
fallback between Stooq (daily-only) and the keyed providers.

### 5. Tiingo — deep EOD history + IEX intraday
**1,000 req/day**, but 50 unique symbols/hour and 500 symbols/month. Long clean
EOD history for backtesting; symbol caps make it a backtest/research source, not
a watchlist driver.

### 6. CoinGecko demo tier — crypto breadth
Free demo key: **10,000 calls/month at 100/min**, 17k+ coins, market caps and
global metrics CCXT exchanges don't expose. Current CCXT chain already covers
OHLCV well; add CoinGecko only if we want market-cap/dominance context.

### 7. Tradier sandbox — free options chains
Free sandbox account: 15-min-delayed equities and **unlimited options chains**.
The most credible replacement for the fragile Yahoo cookie+crumb options path.

## Not worth it (free tier)
- **Alpha Vantage** — now ~25 req/day; too small for anything beyond smoke tests.
- **Polygon (rebranded Massive.com)** free — 5 req/min, EOD/15-min-delayed;
  keep the provider for people who bring a paid key, but the free tier adds
  nothing over Stooq.
- **FMP free** — 250 req/day and key endpoints paywalled; EDGAR covers the
  fundamentals need for free.

## Proposed target chains

```
equity quote:  Yahoo → Alpaca(IEX, free key) → Finnhub → Stooq
equity bars:   Yahoo → Alpaca(free key) → Stooq(daily) → TwelveData
crypto:        Yahoo → CCXT (unchanged)
news:          Finnhub company-news → Yahoo RSS (fallback)
fundamentals:  SEC EDGAR companyfacts (keyless) → Yahoo v10 (fallback)
macro:         FRED (free key)
options:       Tradier sandbox → Yahoo crumb (fallback)
```

## Suggested next steps
1. Create free keys: Alpaca (paper), Finnhub, Twelve Data, FRED, Tradier sandbox;
   put them in `.env` (already git-ignored).
2. Promote `AlpacaProvider` in the chain once keys exist (zero code for quotes/bars).
3. Add `FinnhubProvider` (quote + company news) and wire news fallback.
4. Add an EDGAR client for the valuation module (respect 10 req/s + User-Agent).
5. Add `TwelveDataProvider` for intraday bar fallback with a daily-budget guard.

## Sources
- [Qveris — Stock API Free: 8 options compared (2026)](https://qveris.ai/guides/stock-api-free-comparison/?lang=en)
- [NB Data — Best financial data APIs in 2026](https://www.nb-data.com/p/best-financial-data-apis-in-2026)
- [Alpaca market data docs](https://docs.alpaca.markets/us/docs/about-market-data-api) · [Alpaca data plans](https://alpaca.markets/data)
- [Finnhub pricing](https://finnhub.io/pricing) · [Finnhub docs](https://finnhub.io/docs/api/introduction)
- [Massive (ex-Polygon) rate limits](https://polygon.io/knowledge-base/article/what-is-the-request-limit-for-polygons-restful-apis)
- [FMP pricing](https://site.financialmodelingprep.com/pricing-plans) · [Tiingo pricing](https://www.tiingo.com/about/pricing)
- [SEC EDGAR free API guide](https://tldrfiling.com/blog/free-sec-edgar-api-guide/) · [dev.to on the SEC API](https://dev.to/m0dus/the-sec-has-a-free-financial-data-api-that-nobody-talks-about-dfi)
- [CoinGecko API pricing](https://www.coingecko.com/en/api/pricing) · [CoinGecko free crypto APIs 2026](https://www.coingecko.com/learn/best-free-crypto-api)
- [Next Gen Nexus — best free stock APIs 2026 (tested)](https://thenextgennexus.com/2026/05/15/10-best-free-stock-market-apis-2026/)
- [edgeful — Yahoo Finance API alternatives](https://www.edgeful.com/blog/posts/yahoo-finance-api-alternatives)
- [Why yfinance keeps getting blocked](https://medium.com/@trading.dude/why-yfinance-keeps-getting-blocked-and-what-to-use-instead-92d84bb2cc01)
