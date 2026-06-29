# MVP feature specs — toward a customer app

_Companion to `PRODUCT_STRATEGY.md`. Two highest-leverage net-new features,
specced against the **current** codebase so they're build-ready. Both lean on
assets that already exist (the agent graph, the analytics modules, the order
store, the audit log) rather than greenfield work._

---

## Feature 1 — Trade Journal & Behavioral Analytics _(primary MVP)_

**Why this first.** Market research flags AI-augmented journaling as the highest-
ROI net-new capability: it surfaces patterns a trader wouldn't think to examine
("you size up after wins," "you lose expectancy on trades entered right after a
loss"), and the durable value is *infrastructure* — capturing and organizing
activity — not predicting alpha. It's sticky (the data compounds), it's a clear
upsell, and it's low regulatory risk (it analyzes the user's *own* past
behavior, not forward advice).

**What we already have to build on**
- Every agent run is persisted with a `run_id` and audit events
  (`core/audit.py`, `agent.run.start/end`, `agent.portfolio`).
- Orders carry their full lifecycle + `fill_price`, `est_price`, `risk_pct`,
  `source` ("agent"|"human"), and `run_id` (`execution/orders_store.py`).
- Positions / realized math already exist in `execution/positions.py`.
- Analytics primitives (risk, returns) exist in `analytics/`.

### Scope (MVP)

1. **Auto-journal** — no manual entry. Every `SUBMITTED` order becomes a journal
   entry, linked back to its originating agent run (thesis, direction,
   rationale, risk_pct) when `source == "agent"`. Closing/reducing trades pair
   with their opens to produce realized P&L per round-trip.
2. **Per-trade record** — symbol, side, qty, entry/exit price & time, realized
   P&L, holding period, the thesis/rationale at entry, and whether the user
   followed or overrode the proposed size.
3. **Behavioral metrics** (computed in code, deterministic — same discipline as
   sizing):
   - win rate, average win/loss, expectancy, profit factor;
   - P&L by **day-of-week** and by **time-since-last-loss** (the "revenge trade"
     signal);
   - **size-after-outcome**: average position size after a win vs. after a loss;
   - agent-proposed vs. human-overridden outcomes (does following the agent
     help?).
4. **Insights feed** — a short, ranked list of plain-language observations
   derived from the metrics above ("Your win rate drops to 31% on trades opened
   within 24h of a loss"). Templated from thresholds, **not** LLM-freeformed, so
   they're defensible and reproducible.

### Proposed shape (fits existing layout)

- `backend/app/analytics/journal.py` — pure functions: `pair_round_trips(orders)`,
  `behavioral_metrics(trades)`, `insights(metrics)`. No I/O, fully unit-testable
  with synthetic orders (mirrors how `analytics/backtest.py` is tested).
- `backend/app/api/journal.py` —
  `GET /journal/trades`, `GET /journal/metrics`, `GET /journal/insights`
  (symbol/date filters as query params, per the crypto-`/` convention).
- `frontend/components/Journal.tsx` — a grid tile: round-trip table + metrics
  cards + insights list.

### Acceptance criteria
- Round-trip pairing is correct for partial fills and scale-outs (FIFO).
- All metrics computed in code; zero LLM in the P&L/behavioral path.
- `journal.py` ships with unit tests at the bar set by the analytics suite
  (≥95%), including the size-after-outcome and day-of-week aggregations.
- Insights are deterministic given the same trade history.

### Out of scope (v1)
Multi-broker import (needs the broker-read-sync milestone), tax lots, and any
forward-looking recommendation.

---

## Feature 2 — Natural-language intent → proposal _(the front door)_

**Why.** The single biggest UX shift in the niche is "conversationally ask for
insights" instead of clicking around. It's also the most natural front-end to
the agent graph we already run — and, critically, it stays inside the safety
model: NL produces a **proposal in the approval queue**, never an execution.

**What we already have to build on**
- `agents/graph.py` already runs research → risk → portfolio and emits an order
  *draft*; `api/agents.py` already turns a draft into a `PENDING_APPROVAL` order
  with `source: "agent"`; the SSE stream already narrates each node.

### Scope (MVP)

1. **Intent parse** — a thin LLM step that maps free text
   ("hedge my tech if VIX > 25", "is NVDA a buy here?") into a structured intent:
   `{symbol(s), question, optional condition}`. Sizing/decisions stay in code
   and behind the human gate — the LLM only structures the request.
2. **Route to the existing graph** — feed the structured question into
   `run_research_stream`; reuse the existing SSE console and order-creation path
   verbatim. No new execution code.
3. **Conditional intents** ("if VIX > 25") — v1 records the condition on the
   proposal as a human-readable guard and surfaces it in the approval card; it
   does **not** auto-fire. (Server-side condition monitoring is a fast-follow
   built on the existing `alerts/engine.py`.)

### Proposed shape
- Extend `api/agents.py` with `POST /agents/intent` that calls a new
  `agents/intent.py::parse_intent(text) -> ResearchRequest(+condition)` then
  delegates to the existing research path.
- `frontend/components/AgentConsole.tsx` gains a single prompt box.

### Acceptance criteria
- Ambiguous/unparseable input returns a clarifying response, never a silent or
  wrong order.
- A parsed intent produces exactly the same proposal contract as today's
  `/agents/propose` (still `PENDING_APPROVAL`, still human-approved).
- Intent parsing is mockable in tests (no live LLM needed in CI), matching how
  the agent stream is already tested.

### Out of scope (v1)
Auto-execution of conditions, portfolio-wide multi-symbol baskets, and broker
order routing.

---

## Sequencing

Feature 1 (Journal) ships first — it's lower regulatory risk, compounds value,
and rides existing data. Feature 2 (NL intent) follows as the acquisition-
friendly front door once the trust/correctness foundation
(`TEST_COVERAGE_ANALYSIS.md` P0 items) is in place. Both preserve the
non-negotiable guardrails: sizing in code, every order human-approved, paper by
default.
