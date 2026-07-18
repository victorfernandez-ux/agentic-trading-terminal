# ROADMAP — Vibe-Trading adoption plan (v1.6 — COMPLETE July 15, 2026: Phases A-G all landed)

**Date:** July 13, 2026 · **Source research:** [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading)
README + full [release history](https://github.com/HKUDS/Vibe-Trading/releases) (v0.1.4→v0.1.11) +
third-party field review (andrew.ooo) — see "Lessons from the field review" at the bottom.
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
- Future extension (their v0.1.9 "Research Goal runtime"): long-running goals with per-goal budgets
  and auditable checklists — note only, not in scope for this cycle.
- Tests: lifecycle (open → supported/refuted), link integrity, agent-tool round trip.

**A3. Scan → research loop** *(META item 2)*
Screener top hit (ranked in code) feeds `run_propose` on demand or on a schedule; reuse the alert
loop's sliding-window hourly cap + audit pattern (`ALERT_AUTO_RESEARCH_PER_HOUR` gets a sibling
`SCAN_AUTO_RESEARCH_PER_HOUR`). Each scheduled run opens/updates a hypothesis (A2). Proposals only.
- Touch: `app/analytics/screener.py` (deterministic ranking), `app/alerts/engine.py` or a small
  `app/research/scan_loop.py`, config, audit events `scan.auto_research.*`.
- Scheduled-run state survives restarts (their v0.1.11 "crash-safe atomic job store"): persist
  next-run/last-run in a table, not in-memory — the evaluator already restarts with the process.
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
over the same window — data via the existing keyless Yahoo path. Report excess return **and
information ratio** (their v0.1.6 panel shape: ticker / benchmark return / excess / IR).

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
- Cache staleness rule (their v0.1.10): **never cache a bar range that ends today** — today's bar
  is still forming. Apply to the screener's 15-min bar cache and any new loader cache.
- Tests: chain order, hop logging, Stooq parser on fixtures, symbol normalization, staleness rule.

**C2. Alpha factor pack for the screener.** Cherry-pick 10–20 classic factors: `alpha101`
(Kakushadze, arXiv:1601.00991 — public formulas), a few `qlib158` (Apache-2), and academic ones
(momentum, 52-week-high proximity, Amihud illiquidity).
- New: `app/analytics/factors.py` (pure pandas/NumPy, PIT-safe: only data ≤ bar date), screener
  gains factor-rank conditions; scan loop (A3) can rank by factor score.
- Tests: factor values on hand-computed fixtures, no look-ahead (shift assertions).

**C3. Watchlist correlation heatmap.** Rolling return correlations across the watchlist symbols
(their v0.1.7 dashboard) — one pure function in `analytics/` + a small heatmap in the Analytics
panel. Cheap, and gives the risk agent a concentration signal (`get_correlations` tool).

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

## Phase G — LLM observability & robustness

Motivated by the field review's two sharpest caveats (cost opacity, provider flakiness).

**G1. Per-run LLM usage + cost accounting.** Record provider/model/prompt+completion tokens for
every LLM call in an agent run (their `llm_usage.json` pattern), aggregated per `run_propose` and
written to the audit trail. Go one better than Vibe-Trading (review caveat: "provider-reported
only, no price estimation — you multiply yourself"): keep a small static price table for the
models we actually use and show **estimated cost per proposal** in AgentConsole + SSE payload.
Makes ALERT/SCAN_AUTO_RESEARCH_PER_HOUR caps tunable on real numbers instead of vibes.
- Touch: `app/agents/llm.py` (usage capture on every `complete_json`), `graph.py` (aggregate),
  audit event `agent.llm_usage`; frontend AgentConsole cost line.
- Tests: scripted LLM responses with usage blocks → expected aggregation + cost math.

**G2. LLM call robustness.** Pre-flight response validation + bounded retry on empty/malformed
model output (their `empty_model_response` handling and stream-failure retry). ATT is mostly
shielded by OpenRouter's single API shape, but `complete_json` currently trusts the model: add
one retry on empty/unparseable JSON with the error appended to the prompt, then fail loudly into
the existing error envelope. Judge "invalid direction coerces to none" stays as the last resort.
- Tests: empty response → one retry → typed failure; malformed JSON → repair retry path.

---

## Considered & deferred (from the same research — not adopted now)

- **Vision tool for chart/screenshot reads** (v0.1.11): interesting for chart-pattern evidence,
  but needs a multimodal model + new cost profile. Revisit after G1 gives cost visibility.
- **Pine Script / MetaTrader / vnpy strategy exports** (v0.1.4+): ATT keeps strategy logic in
  code, not user-exportable templates. Revisit if backtest strategies become user-authored.
- **Universal document reader (`read_document`) / `read_url` via Jina**: general-agent tooling;
  ATT's evidence pipeline is deliberately narrow (quotes/bars/news/chains). Skip.
- **Swarm presets / 29-team orchestration**: ATT's fixed research→debate→risk→portfolio graph is
  the product thesis; persona consensus already covers the "committee" angle.
- **Portfolio optimizers (turnover-aware L1, etc.)**: sizing stays deterministic in
  `_build_order` — an optimizer would move sizing authority. Guardrail, not a gap.
- **Multi-market engines (China A/futures/forex/India)**, **QVeris premium data**, **16-adapter
  IM breadth**, **OAuth broker mandates**: out of market scope or guardrail-conflicting (E2/F3
  adopt the safe kernels: one IM adapter, structural paper discriminators).

## Lessons from the field review (andrew.ooo)

Caveats the reviewer hit in practice, and what ATT does about them:
- **Cost transparency incomplete** → G1 ships usage *and* price estimation from day one.
- **Provider quirks bite** (DeepSeek hangs, Kimi UA, Gemini signatures) → ATT stays single-gateway
  (OpenRouter) and adds G2's bounded retries; we do not adopt a 13-provider capability layer.
- **Only one live broker verified end-to-end** → reinforces ATT's paper-only stance: breadth of
  broker connectors is marketing surface; correctness of one gated path is the product.
- **Naming/discoverability** → not our problem to fix, but a reminder: ATT's public README should
  say precisely what it is ("paper-trading research terminal, human-approved proposals").

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
| 8 | C3 correlation heatmap | — | S |
| 9 | G1 LLM usage + cost | — (pull forward anytime; informs cap tuning) | S |
| 10 | G2 LLM robustness | — | S |
| 11 | D1 approver profile | A1 (shared P&L calc) | M |
| 12 | E1 MCP server | stable tool registry | M |
| 13 | E2 Telegram alerts | alerts engine (done) | S |
| F | hardening | continuous; F1/F2 before hosted deploy | S each |

- Working rules unchanged from `META_PROMPT.md`: tests green → commit → next; restart backend after
  backend changes (`start-backend-logged.bat`); `symbol` as query param; small `feat:`/`fix:` commits.
- New deps require justification per item (candidates: `mcp` SDK for E1 only).
- When adapting Vibe-Trading code (MIT): keep their copyright notice in the adapted file's header.
  Analytics remain FinceptTerminal-*clean-room* — that constraint is unchanged and separate.
- After each phase: update `HANDOFF.md`, rewrite `META_PROMPT.md` for the next cycle, tick this file.

---

# Hardening roadmap (v2 — from the July 18, 2026 full-repo audit) — Phases H1–H7

**Source:** four-reviewer audit (git history/process, backend+guardrails, frontend, testing/CI/docs)
run July 18, 2026. Headline: all three guardrails HOLD structurally with no bypass path, backend
suite 302/302 green — but the approval gate's *UI* fails silent, two backend operational landmines
exist, and the frontend has zero tests/lint. This roadmap fixes the findings in risk order.

**Workflow (every phase — uses gstack, see CLAUDE.md):** own branch → implement, tests green →
`/review` on the branch → (phases touching frontend UX: `/qa` against the running app) → PR via
`/ship` or manual — **no direct-to-main**. One PR per phase. Run `/cso` once after H1+H2 land as an
independent security pass.

## Phase H1 — Backend safety hotfixes (branch `fix/backend-safety-hardening`, size S)

- **H1a. LLM client deadline.** Request timeout (~60s) on the OpenRouter/OpenAI client in
  `app/agents/llm.py` (`complete_json` currently has none — a hung provider hangs the run); one
  retry on transient network/5xx/429 (today only unparseable content retries, G2). Test: stubbed
  hanging/failing client → typed `LLMResponseError`, never a hang.
- **H1b. Gate the silent SQLite fallback.** `db.py:_make_engine` silently falls back
  Postgres→SQLite on ping failure — in production that reads as "all data vanished". Allow only
  when `app_env` != production; otherwise fail loudly at startup. Test both branches.
- **H1c. Strict order input validation.** `api/orders.py:OrderProposal`: `side` →
  `Literal["buy","sell"]`, `qty` → `Field(gt=0)`, `order_type` → `Literal`. Tests: qty 0/negative,
  bad side → 422 (today they enter PENDING_APPROVAL and corrupt positions math).
- **H1d. `require_human_approval` honesty.** The flag is decorative (read only by `/health`).
  Startup assertion it is True — no runtime toggle illusion. Keep `/health` reporting.
- **H1e. Constant-time token compare.** `main.py` auth middleware `==` → `secrets.compare_digest`.

## Phase H2 — ApprovalQueue: informed, fail-loud human gate (branch `fix/approval-queue-hardening`, size M)

The backend gate is airtight; the UI in front of it is not.
- **H2a. Fail loud.** `ApprovalQueue.act()` ignores `r.ok` and has no catch — 409/500/network all
  look like success. Check status, catch, render inline per-card error; on 409 refresh to the
  order's real status.
- **H2b. Live queue.** Poll ~10s (Positions pattern) so orders resolved via Telegram/MCP/other tab
  disappear; never render Approve for non-PENDING_APPROVAL.
- **H2c. Informed approval.** Render `est_price` (typed but never shown), order age, and the
  proposing run's rationale — backend: include thesis summary / `run_id` in the order payload.
- **H2d. Confirm affordance.** Two-step approve ("Confirm BUY 3 NVDA ~$1,500?").
- `/qa` the flow end-to-end after landing (approve, reject, forced 409, network-off).

## Phase H3 — Frontend quality infrastructure (branch `chore/frontend-testing-lint`, size M)

- **H3a. ESLint for real.** Flat config (typescript-eslint + react-hooks); the repo already carries
  `eslint-disable` comments for a linter that isn't installed. Fix violations; `npm run lint` in CI.
- **H3b. Vitest + Testing Library.** First targets pin the safety path: ApprovalQueue (success,
  409, network failure, double-click lockout, stale refresh) and `lib/api.ts` (401 event, tickets).
  CI job.
- **H3c. Shared `usePolledFetch` hook.** Replaces six hand-rolled useEffect+setInterval copies and
  the silent `.catch(() => setX([]))` pattern; unified loading/error states.
- **H3d. Shared API types.** `lib/types.ts` (or OpenAPI-generated) — components currently redeclare
  response shapes per-file, so FE/BE drift is invisible.

## Phase H4 — Reproducibility, legal, deploy correctness (branch `chore/repro-license-deploy`, size S–M)

- **H4a. Backend lockfile.** `uv` (or pip-tools) lock committed; CI installs from it. Today's
  floating `>=` bounds are not reproducible.
- **H4b. LICENSE + provenance.** Add LICENSE (MIT per PROJECT_PLAN intent) — docs discuss AGPL
  obligations but no LICENSE file exists. One-time review of `f1fa10c` ("adapted from
  FinceptTerminal's feature set") to confirm clean-room; attribution note in README.
- **H4c. `.env.example` completeness.** Add the knobs the code reads but the example omits:
  `API_TOKEN`, `CORS_ORIGINS`, `KILL_SWITCH_FILE`, `RUNS_DIR`, `TELEGRAM_*`,
  `SCAN_AUTO_RESEARCH_PER_HOUR`, `REFLECTIONS_LIMIT`.
- **H4d. Migrations as source of truth.** Docker entrypoint runs `alembic upgrade head` before
  uvicorn; `create_all` + `_ensure_schema_upgrades` restricted to SQLite dev so the two schema
  paths can't diverge.

## Phase H5 — Typecheck + CI completion (branch `chore/mypy-ci`, size S–M)

- **H5a. mypy enforced.** `[tool.mypy]` config, fix the 52 current errors (`agents/graph.py` first
  — it's the sizing engine), CI step. mypy is a declared dev dep that never runs.
- **H5b. Durable audit fallback.** `audit.py` swallows DB-write failures — an approval's audit row
  can be lost. Append to a local JSONL WAL on DB failure; test by breaking the session.
- **H5c. (Optional)** `pip-audit` / `npm audit` as non-blocking CI steps.

## Phase H6 — Docs truth pass (branch `docs/sync-and-cross-platform`, size S)

- **H6a.** Fix contradictory test counts (README 185 / HANDOFF "5 passing" / META 299 → actual);
  refresh HANDOFF "Verified working".
- **H6b.** Document `backend/run-dev.sh`; Linux/macOS commands alongside Windows in
  README/HANDOFF/CLAUDE.md (README's `.venv\Scripts` paths dead-end non-Windows devs).
- **H6c.** Record the lockfile policy and the "CSS tokens, never hex literals" rule.

## Phase H7 — Maintainability backlog (continuous, no urgency)

Split `Analytics.tsx` (658 lines, `any`-typed island) per-tab with real types · sweep hardcoded hex
into `globals.css` tokens · extract `_build_order` → `agents/sizing.py` · make the alert
auto-research cap crash-safe like the scan loop's · provider HTTP retry/backoff · dedicated tests
for `api/market|research|memory|agents` + `positions.py` P&L · duplicate "Fear & Greed" mobile
heading · document the build-time-only `BACKEND_URL` rewrite footgun.

## Sequencing

| Order | Phase | Depends on | Size | gstack gates |
|---|---|---|---|---|
| 1 | H1 backend safety | — | S | `/review` |
| 2 | H2 approval-gate UI | H2c backend bit | M | `/review` + `/qa` |
| 3 | H3 frontend infra | H2 (tests pin it) | M | `/review` |
| 4 | H4 repro/legal/deploy | — | S–M | `/review` |
| 5 | H5 mypy + CI + audit WAL | — | S–M | `/review` |
| 6 | H6 docs truth | H1–H5 (counts settle) | S | `/review` |
| — | H7 backlog | continuous | S each | `/review` |
| — | `/cso` security pass | after H1+H2 | — | — |

Guardrails unchanged and restated: no autonomous money movement; paper only; sizing in code;
secrets out of git; FinceptTerminal clean-room. After each phase: update `HANDOFF.md`, rewrite
`META_PROMPT.md`, tick this file.
