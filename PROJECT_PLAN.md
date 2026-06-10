# Agentic Trading Terminal — Project Plan & Tooling Research

**Owner:** Victor Fernandez (NextVibe AI)
**Date:** June 10, 2026
**Reference:** [FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal) (C++20/Qt6, 19.4k★)
**Status:** Planning — pre-build

---

## 1. What we're building

An **agentic trading terminal**: a desktop/web application where AI agents do the heavy lifting of research, analysis, and trade preparation, and the human stays in control of execution. It spans **crypto, US equities, and options/derivatives**, with institutional-grade analytics underneath.

The differentiator versus Fincept is the **agentic core**. Fincept ships 37 "persona" agents bolted onto a native analytics suite. We instead make the agent loop the spine of the product: data, analytics, and execution are all *tools the agents call*, and the human supervises through an approval layer rather than clicking through screens.

### Positioning vs. the reference

| | FinceptTerminal | Agentic Trading Terminal (this project) |
|---|---|---|
| Core paradigm | Native analytics suite + agents as a feature | Agent loop is the spine; everything else is a tool |
| Stack | C++20 / Qt6 / embedded Python | Python services + web UI (see §4) |
| Strength | Raw performance, breadth, single binary | Speed to ship, AI-native UX, extensibility |
| Execution model | Manual + algo | Agent-proposed, **human-approved** |
| Build difficulty | Very high (C++/Qt) | Moderate (Python/web) |

### Guardrails (non-negotiable)

- **No autonomous money movement.** Agents *propose*; the human *approves* every live order. This is both a product principle and a safety/compliance requirement.
- **Paper-trading first.** Every broker integration lands in paper mode before live.
- **Auditability.** Every agent decision, tool call, and order is logged and replayable.

---

## 2. MVP scope (what "shipped v1" means)

The full Bloomberg-style breadth is the destination, not the MVP. v1 proves the agentic loop end-to-end on one asset class, then we widen.

**v1 must do:**
1. Pull real-time + historical data for **crypto and US equities**.
2. Render a usable terminal UI — watchlist, charts, positions, an agent chat/console.
3. Run a **multi-agent research loop** (e.g., a research agent, a risk agent, a portfolio agent) that produces a trade thesis with rationale.
4. **Paper-trade** through one broker, with a human-approval step before any order.
5. Log and replay every decision.

**Deferred to later phases:** options strategy builder, live trading, 100+ connectors, backtesting UI, ML/factor lab, node editor.

---

## 3. High-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          UI LAYER                             │
│  Web app (React/Next) — watchlist · charts · positions ·      │
│  agent console · approval queue                               │
└───────────────▲───────────────────────────────▲──────────────┘
                │ WebSocket / REST              │
┌───────────────┴───────────────────────────────┴──────────────┐
│                      APPLICATION / API (FastAPI)              │
│  auth · session · order-approval workflow · audit log         │
└───────┬──────────────────┬───────────────────┬───────────────┘
        │                  │                   │
┌───────▼──────┐  ┌────────▼─────────┐  ┌──────▼──────────────┐
│ AGENT ENGINE │  │  DATA SERVICES   │  │ EXECUTION SERVICES  │
│ (LangGraph)  │  │ market data +    │  │ broker adapters     │
│ research /   │◄─┤ news + fundamentals│ │ (paper → live)      │
│ risk /       │  │ normalization    │  │ order mgmt / OMS     │
│ portfolio /  │  │ caching          │  │ position tracking   │
│ execution    │  └────────┬─────────┘  └──────┬──────────────┘
│ agents       │           │                   │
└──────┬───────┘  ┌────────▼─────────┐  ┌──────▼──────────────┐
       │          │  QUANT / ANALYTICS│  │ EXTERNAL BROKERS    │
       └─────────►│ backtest · risk   │  │ Alpaca / Tradier /  │
   tools the      │ metrics · pricing │  │ crypto via CCXT     │
   agents call    └──────────────────┘  └─────────────────────┘
                                         ┌─────────────────────┐
                                         │ STORAGE             │
                                         │ TimescaleDB (ticks) │
                                         │ Postgres (state)    │
                                         │ Redis (live/cache)  │
                                         └─────────────────────┘
```

The key idea: **the agent engine treats data, analytics, and execution as MCP-style tools.** A new broker or data source is just a new tool registration, not a UI rewrite.

---

## 4. Recommended tech stack

You asked me to recommend. Here's the call and the why.

### Recommendation: Python services + web UI

**Backend: Python 3.12 + FastAPI.** Python owns the quant/AI ecosystem — every library below is Python-first. FastAPI gives async WebSocket support for live data and clean REST for everything else.

**Agent engine: LangGraph.** It's the most production-ready agent framework in 2026 — durable, stateful, graph-based execution with built-in checkpointing and **human-in-the-loop** support, which maps exactly onto our approval requirement. (CrewAI is easier to start with but weaker on checkpointing/control; AutoGen is now in maintenance mode.)

**Frontend: React + Next.js + TradingView Lightning/Lightweight Charts.** Web gives the fastest iteration and the best charting ecosystem. Lightweight Charts is the industry-standard free financial charting lib.

**Data plane:** TimescaleDB (time-series bars/ticks) + Postgres (app state, audit) + Redis (live quotes, pub/sub).

**Why not the alternatives:**
- *Match Fincept (C++/Qt6):* best performance, but C++/Qt is the slowest path to ship and the hardest to staff. For an agent-centric product where the bottleneck is LLM latency, not UI render speed, native C++ buys little. **Not recommended.**
- *Pure Python desktop (PyQt/DearPyGui):* single language is appealing, but the web charting/UI ecosystem is far richer and a web app is trivially shareable/demoable. Reasonable fallback if you specifically want an offline native app.

> If you'd rather ship a desktop binary later, the FastAPI backend can be wrapped with Tauri or packaged with PyInstaller without rearchitecting.

---

## 5. Tooling research (concrete picks with tradeoffs)

### 5.1 Market data

| Provider | Covers | Real-time | Pricing (2026) | Verdict |
|---|---|---|---|---|
| **Polygon.io** | Stocks, options, crypto, FX | Yes (SIP) | Stocks Advanced ~$199/mo; options is a separate higher tier; **free tier** for dev | **Primary for equities/options.** Flat-rate, unlimited calls, clean DX. |
| **Databento** | Stocks, options, futures (60+ venues, direct feeds) | Yes (tick, nanosecond) | Metered ~$100–500/mo | Best tick/L2 fidelity; use later for HFT/research. Metered cost scales aggressively. |
| **Alpaca Market Data** | Stocks, crypto, options | Yes | Bundled free with brokerage; paid tiers for full SIP | Good "free with your broker" baseline for v1. |
| **CCXT / CCXT Pro** | 100+ crypto exchanges | Yes (WebSocket in Pro) | Open-source (Pro is paid addon) | **Primary for crypto data + trading.** One unified API across Kraken, Binance, Coinbase, etc. |

**v1 pick:** Alpaca (bundled) + Polygon free/starter for equities & options; CCXT for crypto. Upgrade Polygon to paid and add Databento when research/tick data matters.

### 5.2 Broker / execution

| Broker | Assets | API style | Paper trading | Verdict |
|---|---|---|---|---|
| **Alpaca** | US stocks, ETFs, 20+ crypto, **options** | Modern REST + WebSocket; official **MCP server** | Yes (default) | **Primary broker for v1.** Commission-free, dev-first, options live, and an MCP server we can plug straight into the agent engine. |
| **Tradier** | Stocks, **options** (options-first) | Clean REST; 120–600 req/min; streaming | Yes (sandbox) | **Best dedicated options execution.** Add when options trading goes live. |
| **Interactive Brokers** | Global everything | TWS API / Client Portal / FIX | Yes | Institutional gold standard; heavier integration. Add for breadth/global later. |
| **Crypto exchanges via CCXT** | Crypto spot/perps | Unified CCXT | Some (exchange testnets) | Crypto execution layer. |

**v1 pick:** Alpaca for equities + crypto + options paper trading (one integration covers all three asset classes and ships an MCP server). Layer in Tradier for serious options and CCXT for native crypto exchange access in Phase 2.

### 5.3 AI agent framework

| Framework | Strength | Production readiness | Verdict |
|---|---|---|---|
| **LangGraph** | Stateful graph, checkpointing, human-in-the-loop, LangSmith observability | Highest | **Chosen.** Maps to our approval workflow. |
| OpenAI Agents SDK | Low-overhead, built-in tracing/guardrails | High (OpenAI-native) | Good for prototypes; less control. |
| CrewAI | Role-based teams, easy to start | Medium (limited checkpointing) | Fast prototyping, weaker durability. |
| AutoGen | Multi-party agent conversation | Maintenance mode | Avoid for new builds. |

**LLM providers:** **OpenRouter** as the primary gateway — one OpenAI-compatible endpoint fronting many models, so we can swap freely without code changes. Default model **DeepSeek V4 Flash** (cheap, fast — well-suited to high-frequency agent tool-calling). Anthropic/OpenAI direct keys and a local Ollama fallback remain available for cost/privacy or higher-reasoning tasks.

### 5.4 Quant / backtesting / analytics

| Library | Role | Verdict |
|---|---|---|
| **VectorBT** | Vectorized backtesting, millions of trades/sec, parameter sweeps | **Research/signal discovery.** Fast strategy exploration. |
| **NautilusTrader** | Event-driven, production-parity execution, latency modeling | **Research→production bridge.** Closes the backtest-vs-live gap. |
| Backtrader | Event-driven, broker integration, mature | Veteran fallback; simpler retail path. |
| **QuantLib** | Derivatives pricing, Greeks, fixed income | Options pricing/risk (matches Fincept's QuantLib suite). |
| pandas / NumPy / Numba / pandas-ta | Indicators, data wrangling | Foundational. |

**Workflow:** VectorBT for discovery → NautilusTrader for realistic execution validation → live via broker adapter.

### 5.5 UI / charts

- **TradingView Lightweight Charts** — free, fast, financial-grade candlestick/indicator charts.
- **React + Next.js + Tailwind/shad-cn** — terminal UI, panels, approval queue.
- **WebSocket** stream from FastAPI for live quotes/positions.

---

## 6. Phased roadmap

| Phase | Timeline (indicative) | Deliverable |
|---|---|---|
| **Phase 0 — Foundations** | Weeks 1–2 | Repo scaffold, FastAPI skeleton, Postgres/Timescale/Redis, Alpaca paper account wired, basic React shell. |
| **Phase 1 — Data + UI** | Weeks 3–5 | Live + historical crypto/equity data ingestion, watchlist, TradingView charts, positions view. |
| **Phase 2 — Agent loop** | Weeks 6–9 | LangGraph engine; research + risk + portfolio agents; tool registry over data/analytics; trade-thesis output in agent console. |
| **Phase 3 — Execution + approval** | Weeks 10–12 | Order-management service, human-approval queue, paper trade end-to-end, full audit/replay log. **= MVP shipped.** |
| **Phase 4 — Options + backtest** | Weeks 13–16 | Tradier options integration, options chains/Greeks (QuantLib), VectorBT backtesting surface. |
| **Phase 5 — Breadth + live** | Weeks 17+ | Live trading (gated), more brokers/data connectors via CCXT/IBKR, ML/factor lab, node-editor workflows. |

---

## 7. Key risks & open decisions

**Risks**
- **Compliance/regulatory:** an app that places real trades has regulatory exposure. Keep live trading behind explicit human approval and consult on licensing before live launch. (We have a `legal:compliance-check` capability available when ready.)
- **LLM reliability:** agents can hallucinate theses. Mitigate with structured tool outputs, risk-agent veto, and mandatory human approval.
- **Data cost creep:** real-time options + tick data gets expensive fast — stage paid tiers to actual need.
- **Licensing of the reference:** FinceptTerminal is AGPL-3.0 + commercial. **Do not copy its code.** Use it only as a feature/architecture reference; build ours independently.

**Open decisions for you**
1. Web app vs. eventual desktop binary — confirm web-first is acceptable for v1.
2. Primary LLM provider (Claude vs OpenAI vs local-first) and budget.
3. Live-trading appetite and timeline (affects compliance work).
4. Team size / who's building — changes the timeline above.

---

## 8. Immediate next steps

1. Confirm the stack recommendation (§4) and MVP scope (§2).
2. Stand up the Phase 0 repo scaffold (I can generate this next).
3. Create Alpaca paper-trading + Polygon dev accounts (free).
4. Decide LLM provider + budget.

> Tell me which of these to start and I'll generate the repo scaffold or drill deeper into any section.
