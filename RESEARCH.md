# Deep research — what separates world-class terminals (June 11, 2026)

Five-angle research pass (terminal feature anatomy · keyless data sources · agentic
patterns · screeners/alerts · global Yahoo coverage). Endpoint claims were verified
live on 2026-06-11 from a datacenter IP. This file is the durable record; the
prioritized backlog lives in META_PROMPT.md.

## The synthesis

World-class terminals = **awareness** (news, calendars, movers) + **discovery**
(search, screeners) + **vigilance** (alerts) + **accountability** (portfolio
analytics) layered on top of **analysis**. We had the analysis layer (indicators,
risk, backtests, DCF, personas, options Greeks); v1.4 adds the first three pillars'
foundations: news, global search, and the screener.

## Verified data-source matrix (2026-06-11)

| Source | Status | Use |
|---|---|---|
| Yahoo v8 chart | keyless ✅ | bars/quotes (in prod) |
| Yahoo v8 **spark** | keyless ✅, **cap 20 symbols/req** | batch watchlist quotes (v1.4) |
| Yahoo v1 **search** | keyless ✅ | global symbol search (v1.4) — ASCII-only queries |
| Yahoo **RSS** per symbol | keyless ✅ (survived the 2023 lockdown) | news panel + agent evidence (v1.4) |
| Yahoo v7 options / v10 quoteSummary | cookie+crumb ✅ (we do the dance) | chains (shipped); fundamentals (future) |
| Yahoo predefined screeners + trending | keyless ✅ | whole-market movers (future) |
| SEC EDGAR companyfacts/submissions | ✅ needs User-Agent w/ contact, 10 req/s | real fundamentals + filings feed (future) |
| DBnomics | keyless ✅ (IMF/OECD/Eurostat/BIS aggregated) | macro dashboard (future) |
| World Bank API | keyless ✅ | macro (annual) |
| ECB data-api.ecb.europa.eu | keyless ✅ (old sdw-wsrest host is DNS-dead) | EUR rates/FX |
| alternative.me Fear&Greed | keyless ✅ | crypto sentiment widget (future) |
| FRED | API key required (free); fredgraph.csv IP-filtered | macro (needs key) |
| CNN Fear&Greed | 418 bot-wall without full header spoof | degradation-only |
| Stooq | proof-of-work bot wall (2025+) | avoid |
| Google News RSS | works but explicit non-commercial clause | avoid |

Rate-limit reality (community evidence: yfinance #2125/#2128/#2297): no documented
limits; ~360 req/hr commonly cited as the soft ceiling; throttling is pattern-based;
bans temporary. Mitigations now in code: spark batching (1 req per ≤20 symbols),
15-min bar cache in the screener, Semaphore(4)+jitter cold scans, Mozilla-prefixed UA.

Global symbol space (verified): exchange suffixes (.L .T .DE .PA .NS .SS .HK .KS
.AX .TO .SA …), FX `EURUSD=X`, indices `^GSPC/^FTSE/^N225`, futures `ES=F GC=F CL=F`,
treasury yields `^TNX`. Sub-unit currency trap: GBp/ZAc/ILA quote in pence/cents —
divide by 100 before any cross-market position math (relevant when sizing leaves USD).

## Agentic patterns (from ai-hedge-fund, TradingAgents arXiv:2412.20138, FinMem)

Ranked adoption order for future cycles:
1. **Parallel evidence fan-out** — run technical/risk/personas/news as parallel tool
   nodes writing structured evidence; zero extra LLM tokens. (research_node already
   attaches indicators + headlines serially as of v1.4.)
2. **Deterministic vol/correlation-aware sizing** in `_build_order` (ai-hedge-fund's
   risk_manager bands: vol-scaled 5–25% position limits, correlation multiplier) —
   strengthens the sizing-in-code guardrail.
3. **Bull/bear debate, exactly 1 round, judge must commit** (TradingAgents default;
   anti-"Hold by default" instruction is the decision-quality lever; cheap model for
   debaters, strong model for judge). Shows the approver the best case AGAINST.
4. **Reflection memory from the audit log** — we already persist every run/fill;
   add realized-P&L reflections injected into future prompts (start SQL-recency,
   upgrade to BM25 if needed).
5. **Scan → rank in code → agent researches top hit** (cap auto-runs/hour; proposals
   only — the approval gate is untouched). Screener (v1.4) is stage 1 of this loop.

## What we deliberately skip

Chat/community (network-effect-locked), generic AI-copilot dashboards (our scoped
agent pipeline is stronger), Fincept-style breadth (maritime/satellite — marketing,
not daily use), multi-round debates (>1 round adds tokens, not quality), 3-agent
LLM risk debate (sizing stays deterministic code).

Full citations live in the session log; key ones: NYU Bloomberg command guide,
TradingView alert/screener docs, thinkorswim manual (Stock Hacker/Alerts/Calendar),
Finviz screener docs, yahoo-finance2 endpoint map, yfinance issues #2125/#2128/#2297,
TradingAgents repo+paper, virattt/ai-hedge-fund, OpenBB agents-for-openbb, FinMem.
