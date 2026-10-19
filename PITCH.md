# Agentic Trading Terminal — Capabilities Pitch

**AI agents do the research. You keep the keys.**

The Agentic Trading Terminal (ATT) is an open-source trading workstation where a team of AI agents
researches markets, debates the thesis, sizes the risk, and drafts the order — and a human approves
every single trade before anything executes. Paper trading only, fully audited, end to end.

This document is the tour. Everything below is shipped and covered by the test suite — nothing here
is roadmap.

---

## The idea in one paragraph

Every trading terminal bolts AI onto a wall of charts. ATT inverts that: the **agent loop is the
spine** of the product, and data, analytics, and execution are tools the agents call. You ask a
question ("Is NVDA a buy here?") or let an alert or market scan trigger the question for you. A
research agent gathers evidence, a bull and a bear argue the case, a judge commits a direction, a
risk agent sizes or vetoes, and a portfolio agent drafts a concrete order — which lands in an
approval queue and goes nowhere until you click Approve. The human is not a spectator; the human is
the gate.

---

## What the agents can do

**Parallel evidence gathering.** One fan-out collects live quotes and bars, technical indicators,
risk metrics, investor-persona consensus, news headlines, and the approver's own track record on the
symbol — before a single LLM token is spent.

**Adversarial debate.** Research feeds a one-round bull-vs-bear debate; a judge weighs both cases and
commits a direction. The console renders both sides, so the approver always sees the best argument
*against* the trade. Debaters can run on a cheaper model than the judge.

**Deterministic sizing — in code, never by the LLM.** Position size is computed from notional × risk%
÷ price, scaled by ATR volatility bands, with anti-pyramiding on same-direction adds. The model
proposes a direction; arithmetic decides the quantity.

**Memory that learns from outcomes.** When a position round-trips, a reflection engine replays the
fills, computes realized P&L, and stores a lesson quoting the entry thesis. The next run on that
symbol reads its own history.

**A hypothesis registry.** Theses are first-class objects — open, supported, refuted, or expired —
linked to the agent runs and orders that tested them, with outcomes read off realized P&L.

**Self-starting research, capped.** Price/RSI alerts and a market screener can trigger research runs
autonomously — but each loop has a crash-safe hourly budget cap, every skipped run is audited, and
the output is always just a proposal in the queue.

**Cost transparency.** Every run reports LLM calls, tokens, and estimated cost, per model, in the
console and the audit log.

## The analytics arsenal

A full clean-room analytics suite (FinceptTerminal-inspired, zero code copied) powers both the UI
panels and the agent tools — the agents cite the same engines you can inspect:

- **Technical:** SMA/EMA/RSI/MACD/Bollinger/ATR with a composite signal vote.
- **Risk:** Sharpe, Sortino, VaR/CVaR, max drawdown, beta/alpha vs SPY.
- **Backtesting with a credibility layer:** SMA-cross / RSI-reversion / buy-hold strategies,
  fee-aware and lookahead-free — then walk-forward validation, bootstrap confidence bands, and a
  benchmark comparison vs buy-and-hold, saved as reproducible run cards (inputs + seed + engine
  version). Agents cite the validated numbers, not the raw curve.
- **Valuation:** DCF fair value with a WACC × growth sensitivity grid.
- **Investor personas:** rule-based Buffett, Graham, Lynch, Munger, and Marks scores with a consensus.
- **Options:** live Yahoo chains with clean-room Black-Scholes Greeks and implied vol.
- **Alpha factors:** 12 point-in-time-safe classics (12-1 momentum, 52-week-high, Amihud
  illiquidity, and more) flowing into the screener.
- **Screener:** 13 screens over S&P 100, indices, FX, futures, and crypto universes.
- **Correlations:** watchlist Pearson heatmap with a concentration signal.
- **Behavior mirror:** a shadow profile of *you* — approval rates, win rate, disposition-effect
  detection, and the counterfactual P&L of everything you rejected.

## The terminal

- Global symbol search across 40+ exchanges, FX, indices, futures, and crypto, with a persistent
  watchlist and batched WebSocket quote streaming.
- TradingView-grade candlestick charts, live positions with unrealized P&L, per-symbol news, and a
  Fear & Greed gauge for stocks and crypto.
- An agent console that streams every reasoning step live over SSE — research, debate, risk,
  portfolio — with the full debate transcript.
- A server-side alerts engine with true crossing semantics, cooldowns, and one-shot alerts.
- An installable mobile PWA: bottom-tab phone shell where the quote stream and agent stream survive
  tab switches.
- Telegram notifications for fired alerts and new proposals — a link back to the app, never an
  approve button. Approval never leaves the terminal.
- An **MCP server** exposing the whole tool registry to any MCP-capable client (Claude, IDEs, other
  agents) — propose-only by construction: no approve/execute tool exists at that surface, and a test
  pins it.

## Safety is architecture, not policy

The guardrails are implemented, tested, and in several cases structurally impossible to bypass:

- **No autonomous money movement.** Agents, alerts, scans, and MCP clients can only create
  `PENDING_APPROVAL` orders. A human approves each one, behind a two-step confirm.
- **Paper only.** The live broker path raises `NotImplementedError`; the broker factory structurally
  asserts the adapter is a paper adapter and fails closed. Both are pinned by tests.
- **Kill switch.** Touch one file and every submission halts, claimed orders return to the queue,
  and the halt is audited.
- **Append-only audit log with replay.** Every decision, tool call, fill, fallback, and skipped run
  is recorded; any agent run can be replayed end to end. WAL fallback if the DB write fails.
- **Cost caps everywhere.** Alert-triggered, scan-triggered, and manual research all have crash-safe
  hourly budgets counted from the audit trail.
- **Hardened for hosting.** Token auth with constant-time compare, one-time single-use auth tickets
  for streams, CSRF origin guard, CORS lockdown, a production boot that refuses to start unlocked,
  and a read-only non-root Docker image.

## Engineering you can check

- **333 backend tests** (pytest, fully offline/mocked, ~15s) covering the approval gate's race
  conditions, the paper-only fail-close, sizing bands, audit replay, streaming, the scripted debate,
  and the entire analytics suite — plus frontend Vitest and ESLint, ruff, and mypy, all gated in CI.
- Locked dependencies, Alembic migrations, SQLite by default with a Postgres path, and a
  provider-fallback data chain (Yahoo → Stooq → keyed providers) where every fallback hop is audited.
- MIT licensed, public repository, secret scanning and push protection on.

## What ATT is not

No live trading (deliberately unimplemented), no autonomous execution, no financial advice. It is a
research-and-decision instrument that treats the human approval gate as the product's most important
feature — and a working demonstration that "agentic" and "safe" can be the same architecture.

---

**Run it:** two terminals — `backend/run-dev.sh` (or `.ps1`) and `npm run dev` in `frontend/` — then
open http://localhost:3000 and put an OpenRouter key in `backend/.env`. Full instructions in the
[README](./README.md); architecture and status in [PROJECT_PLAN.md](./PROJECT_PLAN.md) and
[HANDOFF.md](./HANDOFF.md).
