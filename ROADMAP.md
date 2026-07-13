# ROADMAP — Vibe-Trading adoption plan (v1)

**Date:** July 13, 2026 · **Source research:** [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)
(MIT — unlike FinceptTerminal we MAY read and adapt its code, keeping the copyright notice; attribute
adapted implementations in the file header). This roadmap sequences every adoptable element from that
research into ATT development cycles. It extends — does not replace — `META_PROMPT.md`; Phase A *is*
the current META cycle, enriched with Vibe-Trading references. Update `HANDOFF.md` and this file as
phases land.

## Guardrails (unchanged, restated because several items brush against them)

- No autonomous money movement. Everything below produces **proposals**; the human-approval gate in
  `app/api/orders.py` stays load-bearing. MCP/IM surfaces may *read* and *propose*, never approve.
- Paper only — `app/execution/broker.py` live path keeps raising `NotImplementedError`.
- Sizing stays in code (`graph._build_order`). LLM never sizes, never approves.
- Vibe-Trading's Robinhood autonomous-mandate path is explicitly **not adopted** — only its
  containment patterns (kill switch, fail-closed guard, structural paper/live discriminators).

---

## Phase A — Memory & research loop (current META cycle, enriched)

**A1. Reflection memory from the audit log** *(META item 1)*
When a position closes, compute realized P&L from the audit trail and store a short reflection
(symbol, direction, thesis summary, outcome, one-line lesson). Inject the last N reflections for the
symbol into the debate/judge prompts.
- New: `app/memory/reflections.py` (store + retrieval), table `reflections` (Alembic migration).
- Retrieval: SQL recency first. If quality demands it, **SQLite FTS5/BM25** — Vibe-Trading's memory
  module is a working MIT reference for the FTS5 half (their `memory` tools: add/search/forget).
- Wire-in: `graph.py` debate/judge prompt assembly; audit event `memory.reflection.created`.
- Tests: crafted audit history → expected reflection; retrieval ordering; prompt injection capped.

**A2. Hypothesis registry**
First-class `hypothesis` table linking idea → agent runs → orders → realized outcome, mirroring
Vibe-Trading's `create_hypothesis` / `update_hypothesis` / `link_backtest` tools.
- New: `app/research/hypotheses.py`, `/research/hypotheses` CRUD, migration; `run_propose` gains an
  optional `hypothesis_id` stamped through to the order row and audit events.
- Agent tools: `create_hypothesis`, `update_hypothesis` (status only — evidence comes from links).
- Why before A3: gives the scan loop somewhere durable to record *why* a symbol was researched, and
  gives A1's reflections richer raw material.
- Tests: lifecycle (open → supported/refuted), link integrity, agent-tool round trip.

**A3. Scan → research loop** *(META item 2)*
Screener top hit (ranked in code) feeds `run_propose` on demand or on a schedule; reuse the alert
loop's sliding-window hourly cap + audit pattern (`ALERT_AUTO_RESEARCH_PER_HOUR` gets a sibling
`SCAN_AUTO_RESEARCH_PER_HOUR`). Each scheduled run opens/updates a hypothesis (A2). Proposals only.
- Touch: `app/analytics/screener.py` (deterministic ranking), `app/alerts/engine.py` or a small
  `app/research/scan_loop.py`, config, audit events `scan.auto_research.*`.
- Tests: cap enforcement, ranking determinism, hypothesis linkage, evaluator isolation (a failing
  run never kills the loop).

**A4. Frontend: portfolio switcher** *(META item 3, unchanged)*
Dropdown over `/portfolios`; ApprovalQueue + Positions filter by selection; default preserves
today's view.

---

## Phase B — Backtest credibility layer

Adapted from Vibe-Trading's validation stack; strengthens what the debate/judge can cite.

**B1. Run cards.** Every backtest run writes `run_card.json` (+ rendered Markdown): params, data
window, metrics, engine version, artifact paths. Deterministic + reproducible.
- Touch: `app/analytics/backtest.py`; store under `.private/runs/` (gitignored) with a
  `GET /analytics/backtest/runs` index endpoint.

**B2. Walk-forward validation.** Split train/test windows, roll forward, report per-window and
aggregate metrics; flag strategies that only work in one regime.

**B3. Monte Carlo + bootstrap confidence intervals.** Resample trade sequences; report P5/P50/P95
final equity and max-drawdown bands instead of single-point metrics.

**B4. Benchmark panel.** Compare every run against buy-and-hold SPY (equities) / BTC-USD (crypto)
over the same window — data via the existing keyless Yahoo path.

- All B items: pure functions in `analytics/` (clean-room OK to consult MIT source), exposed through
  the existing `/analytics/backtest` endpoint (new optional flags), rendered in the Analytics panel
  (equity-curve chart gains CI bands + benchmark overlay). Research agent's backtest tool gains the
  validated metrics so debate evidence includes "walk-forward holds / breaks".
- Tests: golden-master runs on fixture bars; CI bounds sanity; benchmark alignment.

---

## Phase C — Data & signal breadth

**C1. Provider fallback chain, formalized.** Refactor `app/data/providers.py` to an ordered,
per-market chain (Vibe-Trading pattern: least-ban-risk first, key-gated last, **no silent
fallback** — every fallback hop is logged/audited).
- Add **Stooq** as the second keyless equities source (CSV over HTTPS, no auth) — the concrete
  answer to "Yahoo throttles / dev network blocks exchanges".
- Tests: chain order, hop logging, Stooq parser on fixtures, symbol normalization.

**C2. Alpha factor pack for the screener.** Cherry-pick 10–20 classic factors: `alpha101`
(Kakushadze, arXiv:1601.00991 — public formulas), a few `qlib158` (Apache-2), and academic ones
(momentum, 52-week-high proximity, Amihud illiquidity).
- New: `app/analytics/factors.py` (pure pandas/NumPy, PIT-safe: only data ≤ bar date), screener
  gains factor-rank conditions; scan loop (A3) can rank by factor score.
- Tests: factor values on hand-computed fixtures, no look-ahead (shift assertions).

---

## Phase D — Approver shadow profile (differentiator)

Vibe-Trading's Shadow Account profiles a trader from broker journals. ATT already owns a superior
journal: the append-only audit log of every proposal, approval, rejection and paper fill.

**D1. Behavioral profiling of the human approver.**
- Metrics: approval rate by direction/symbol/agent-confidence, outcome of approved vs rejected
  proposals (counterfactual P&L of rejections via later bars), holding time, disposition effect
  (cutting winners early / riding losers), overtrading windows.
- New: `app/analytics/behavior.py` + `GET /analytics/behavior`; frontend Behavior tab (cards +
  one chart); reflections (A1) gain an approver-pattern line so the judge can say "you historically
  reject shorts here and the rejects outperformed".
- Strictly read-only analytics; no gate changes. Tests: crafted audit trails → expected metrics,
  counterfactual P&L math.

---

## Phase E — New surfaces (propose-only by construction)

**E1. MCP server over the agent tool registry.** Expose ATT's existing tools (quotes, bars,
technical, risk, screener, news, options chain, fear&greed, backtest, `run_research`,
`propose_order`) via MCP (stdio + SSE) so Claude Desktop / other agents can drive research.
- Approval gate is untouched: MCP callers can create PENDING_APPROVAL orders at most. No
  approve/execute tool is ever exported. Auth: reuse `API_TOKEN`.
- New: `app/mcp/server.py` (official `mcp` Python SDK), launch script; docs.
- Tests: tool schema snapshot, propose-only surface (no approval tool present), auth required.

**E2. Telegram alert delivery (first IM adapter).** Push fired alerts and new PENDING_APPROVAL
notifications to a Telegram chat via bot API (stdlib HTTPS, no heavy SDK). Message links back into
the PWA to approve — **never approve in chat**.
- New: `app/notify/telegram.py` + config (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, off by
  default); hook points: alert evaluator fired-event path + `orders.create_pending`.
- Design keeps a thin `notify` interface so Discord/Slack adapters are additive later
  (Vibe-Trading's 16-adapter runtime is the reference for the interface shape, not the scope).
- Tests: payload formatting, disabled-by-default, failure never blocks the evaluator/order path.

---

## Phase F — Hardening track (continuous; pull items forward before any hosted deploy)

**F1. One-time SSE/WS auth tickets.** Replace long-lived `?token=` in URLs with short-lived
single-use tickets minted by an authenticated `POST /auth/ticket` (Vibe-Trading pattern). Keeps
tokens out of logs/history. Fallback to `?token=` stays until frontend migrates.

**F2. API hardening pass.** CSRF rejection for cross-site unsafe methods (before CORS), path/input
validation on any file-ish params, auth-gated settings-style writes. Audit `.env`-driven knobs.

**F3. Structural paper/live discriminators.** Broker adapter asserts paper-ness structurally
(paper account-id pattern / demo flag / sandbox host), not just via config boolean; mismatch
fail-closes. Add a filesystem kill-switch file check before any (paper) submission — cheap now,
load-bearing if live ever ships.

**F4. Docker hardening.** Multi-stage build, non-root user, read-only rootfs, pinned digests,
named volume for the SQLite file — aligns `docker-compose.yml` with the hosted-deploy checklist
(API_TOKEN + CORS lockdown + off-SQLite remain prerequisites from META item 4).

---

## Sequencing & rules

| Order | Item | Depends on | Size |
|---|---|---|---|
| 1 | A1 reflections | — | M |
| 2 | A2 hypotheses | — | S–M |
| 3 | A3 scan loop | A2 (linkage), screener | M |
| 4 | A4 portfolio switcher | — | S |
| 5 | B1→B4 backtest credibility | — | M–L |
| 6 | C1 fallback chain + Stooq | — | S–M |
| 7 | C2 alpha factors | C1 helpful, not required | M |
| 8 | D1 approver profile | A1 (shared P&L calc) | M |
| 9 | E1 MCP server | stable tool registry | M |
| 10 | E2 Telegram alerts | alerts engine (done) | S |
| F | hardening | continuous; F1/F2 before hosted deploy | S each |

- Working rules unchanged from `META_PROMPT.md`: tests green → commit → next; restart backend after
  backend changes (`start-backend-logged.bat`); `symbol` as query param; small `feat:`/`fix:` commits.
- New deps require justification per item (candidates: `mcp` SDK for E1 only).
- When adapting Vibe-Trading code (MIT): keep their copyright notice in the adapted file's header.
  Analytics remain FinceptTerminal-*clean-room* — that constraint is unchanged and separate.
- After each phase: update `HANDOFF.md`, rewrite `META_PROMPT.md` for the next cycle, tick this file.
