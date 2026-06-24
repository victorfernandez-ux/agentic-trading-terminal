# Test Coverage Analysis & Improvement Proposal

_Generated 2026-06-24. Backend `backend/app`, 130 tests passing, **81% line coverage**
(1955 statements, 364 missed) measured with `pytest --cov=app`._

## How to reproduce

```bash
cd backend
pip install -e ".[dev]" pytest-cov
python -m pytest -q --cov=app --cov-report=term-missing
```

## Where we stand

The suite is genuinely strong in the **analytics** and **order-lifecycle**
layers — the deterministic, in-code logic that the project treats as
load-bearing:

| Area | Coverage | Notes |
|---|---|---|
| `analytics/backtest` | 100% | synthetic-bar tests, no network |
| `analytics/personas` | 99% | |
| `analytics/screener` | 97% | |
| `analytics/risk` | 96% | |
| `analytics/options` / `valuation` | 94% / 93% | |
| `analytics/technical` | 91% | |
| `execution/orders_store` | 88% | approve/reject **race** invariants well covered (`test_approve_race.py`) |
| `agents/graph` `_build_order` sizing | 89% | notional cap, vol band, anti-pyramiding all tested |

That order-sizing and approve-race coverage is exactly the right instinct —
those are the guardrails. The gaps below are about **finishing that same job**
for the other guardrails and for the I/O layer.

## Gaps, prioritized by risk

### P0 — Guardrails that are asserted in prose but not in tests

These map directly to the "non-negotiable guardrails" in `CLAUDE.md`. Each is
financial-correctness or safety code with **no direct test**.

1. **Live-broker refusal is untested** — `execution/broker.py:43`.
   The guardrail "live broker path raises `NotImplementedError`" has no test
   that asserts it. `get_broker()` with `settings.trading_mode == "live"`
   should raise; `PaperBroker.submit()` should return a simulated fill and
   never place a real order. This is a one-file, no-network test and arguably
   the single most important missing assertion in the repo.

2. **Position / P&L math is untested** — `execution/positions.py` (50%).
   `get_positions()` (lines 30–56) is the live unrealized-P&L engine and has
   **zero** direct coverage; only the synchronous `_aggregate` helper is hit
   indirectly via sizing tests. Untested behaviors that involve real money math:
   - weighted average cost across multiple fills,
   - signed quantity on `sell` fills (short/flatten),
   - flat-position skip (`abs(qty) < 1e-9`),
   - `market_value` / `unrealized_pnl` = `None` when the live quote fails,
   - `unrealized_pnl_pct` guard when `avg_cost == 0`.
   All testable by seeding the order store and monkeypatching `get_provider`.

3. **approve() broker-failure rollback is untested** — `orders_store.py:107–111`.
   The "broker raised after we claimed the order → release it back to
   `PENDING_APPROVAL` so a human can retry" path, and the live-quote
   `fill_price` fallback (116–120), are never exercised. The race tests cover
   the happy path and double-approve; they don't cover a failing broker.

### P1 — Data layer (largest untested surface, all mockable)

4. **`data/providers.py` (58%, 75 lines missed)** — the failover core.
   - `FallbackProvider._try` provider-rotation / "all failed" `RuntimeError`,
   - `get_quotes_batch` spark-endpoint parsing and per-symbol degradation
     when spark misses or errors,
   - `CCXTProvider._run` exchange rotation and the `_WORKING_EXCHANGE` cache,
   - **`get_provider` routing** — crypto → Yahoo+CCXT, equity chain that
     conditionally appends Alpaca/Polygon based on configured keys.
   Routing and fallback are pure logic; with `httpx`/client mocks these need
   no network and would lift the single biggest cold spot in the codebase.

5. **`agents/tools.py` (36%)** — thin wrappers, but with real branches:
   the benchmark-bars fallback in `get_risk_tool`, the ATM trim/sort/project
   in `get_option_chain_tool`, and the screener field projection. Testable by
   monkeypatching the underlying provider/analytics calls.

### P2 — API graceful-degradation paths

6. **`api/market.py` (68%)** — the deliberate "return `{...,"error":...}` with
   HTTP 200 instead of a 500" branches for `quote`/`bars`/`search`/`news` are
   untested. This is a designed UX contract ("show the reason instead of going
   blank") with no test pinning it.

7. **`api/agents.py` (69%)** — `/research` and `/propose` exception handling
   (error-payload shape) and the `/propose` path that turns an agent `order`
   draft into a `PENDING_APPROVAL` record (with `source: "agent"`) are
   untested, as is the order-creation branch inside the SSE stream.

### P3 — Lower priority

8. **`agents/llm.py` (27%)** — provider selection
   (openrouter / openai / ollama / unsupported), `is_configured()`, and the
   defensive JSON extraction in `complete_json` (stripping prose/fences). All
   pure logic, testable by mocking the OpenAI client — no network or key.

9. **`data/options_chain.py` (23%)** — the Yahoo cookie+crumb dance is
   genuinely hard to test hermetically; a fixture-driven parse test for
   `fetch_chain`'s normalization is the pragmatic win. Leave the network dance
   to integration tests.

10. **`agents/run_demo.py` (0%)** — a developer demo script; reasonable to
    exclude from coverage rather than test.

## Cross-cutting recommendations

- **Add a coverage floor in CI.** `pyproject.toml` configures pytest but sets
  no minimum. Add `--cov=app --cov-fail-under=80` (then ratchet upward) so the
  current 81% can't silently regress.
- **Keep new tests hermetic.** The reason the data/API layers are cold is that
  testing them means faking I/O. Standardize on monkeypatching `get_provider`
  / `httpx.AsyncClient` (the analytics tests already model the
  "synthetic-input, no-network" discipline well) so the suite stays fast and
  deterministic.
- **Exclude demo/scripts** from the coverage denominator (`run_demo.py`) via
  `[tool.coverage.run] omit` so the metric reflects shipping code.

## Suggested order of work

1. P0 #1 broker live-refusal + #2 positions P&L — small, highest safety value.
2. P0 #3 approve() rollback — closes the order-lifecycle story.
3. P1 #4 provider routing/fallback — biggest coverage gain, all mockable.
4. P2 #6/#7 API degradation paths — lock in the UX contracts.
5. Add `--cov-fail-under` once the above land.
