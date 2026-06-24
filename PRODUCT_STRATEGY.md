# From scaffold to a top customer app — product strategy

_Companion to `TEST_COVERAGE_ANALYSIS.md`. Grounded in market research (June 2026)
and the actual architecture of this repo. Sources listed at the bottom._

## TL;DR

The market is splitting into two camps: **black-box auto-trade bots / fully
autonomous agents** (Robinhood Agentic Trading, the bot farms) and
**transparent human-in-the-loop co-pilots**. Retail trust, the CFTC, FINRA and
the SEC are all pushing toward the second camp. **This codebase is already built
as the second camp** — human approves every order, sizing is in code, every run
is auditable, paper-first. That is the moat. The job is not to re-architect; it
is to harden, productize, and position what already exists as **"the Glass Box
trading co-pilot."**

The test-coverage findings are not a side quest — they are the **trust
foundation** of a money app. The exact gaps flagged (positions/P&L math,
live-broker refusal, approval rollback) are the financial-correctness and safety
paths a paying customer is implicitly trusting. "Our order math and safety gates
are provably tested" is a marketable claim, not just hygiene.

## What people in this niche actually need (research-backed)

1. **Remove emotional/behavioral bias** — emotional decisions cost retail
   traders the most; users want a calm, data-driven second opinion.
2. **Plain-language research + explainability** — "compress hours of research
   into minutes," explain setups in plain English, think through an idea
   *before* risking capital. (Your research→risk→portfolio graph already
   produces a thesis + rationale.)
3. **Scan/rank at scale, but the decision stays human** — they reject black
   boxes; they want AI to surface and rank, then *they* pull the trigger.
   (Your approval gate is this, literally.)
4. **Performance & behavioral analytics / journaling** — surfacing patterns
   like "you size up after wins," "you lose after a red Friday." High demand,
   and you already have analytics modules to build on.
5. **Multi-broker data parsing** — eliminating hours of weekly cleanup; the
   durable value is infrastructure, not magic alpha.
6. **Transparency & control** — clear boundaries, the ability to intervene,
   set risk thresholds and escalation rules.

Your current guardrails map **1:1** onto this list. That alignment is the whole
thesis.

## Positioning: the "Glass Box" co-pilot

| Axis | Black-box bots / auto-agents | **This product** | Bloomberg / pro terminals |
|---|---|---|---|
| Who decides | the AI | **the human, every order** | the human |
| Transparency | opaque | **full rationale + audit trail** | high, but $$$ and complex |
| Safety | "trust me" | **paper-first, code-sized, live gated** | n/a |
| Price | low/΅free or opaque | **prosumer subscription** | institutional |
| Trust story | weak (CFTC warns on bots) | **strongest in the category** | strong but inaccessible |

Tagline direction: _"An AI analyst team that does the research and sizing — and
never trades without your yes."_

## Who the customer is (recommended segment)

**Serious self-directed retail + "prosumers," and small RIAs as a B2B2C upsell.**
- Not institutions — Bloomberg/AlphaSense own that, and it's a different sale.
- Not passive investors — robo-advisors own that.
- The sweet spot is the active retail trader who wants an *edge and a
  discipline layer* but refuses to hand over the keys. That is precisely who
  rejects black-box bots and precisely who your architecture serves.

## The gap: scaffold → top customer app

Ordered as a roadmap. Items 1–3 are non-negotiable before charging money.

1. **Correctness & safety foundation** _(the test work)._ A money app's
   reputation dies on one wrong P&L number or one order that shouldn't have
   fired. Land the P0 tests (positions/P&L, live-broker refusal, approval
   rollback) and add a CI coverage floor. This is table stakes and a sales
   asset.
2. **Multi-tenancy: accounts, auth, isolation.** Today it's single-user with a
   local SQLite. Real users need auth, per-user data isolation, and a hosted
   Postgres path (the data layer already supports Postgres).
3. **Compliance layer.** Clear "**not investment advice / educational & decision-
   support**" framing, audit-log export, data-privacy controls, and
   marketing-rule-safe claims (the SEC has fined firms for overstating "AI"
   capabilities). Keep paper as the default and require explicit, gated consent
   for any broker connection. The audit trail you already emit is a compliance
   feature — surface it.
4. **Broker connectivity, safely.** Start **read-only** (import positions/fills
   so P&L and journaling reflect reality), then approval-gated live execution
   behind explicit opt-in. The approval gate makes this a notification UX, not
   an autonomy risk.
5. **Performance + behavioral analytics / journaling.** Highest-ROI net-new
   feature per the research, and adjacent to your existing analytics modules.
   Auto-journal every proposal+outcome (you already store runs) and surface
   behavioral patterns.
6. **Natural-language intent → proposal.** "Hedge my tech if VIX > 25" →
   research → risk → a *proposed* order in the approval queue. You have the
   agent graph; this is a front-door, not a rebuild.
7. **Mobile + push approvals.** The approval gate is inherently a
   notify-and-confirm flow — perfect for mobile push. This is where the
   "co-pilot that pings you" experience lives.
8. **Onboarding & education.** Lower the activation cliff; paper-trading mode is
   a natural, safe first-run experience.

## Monetization

Hybrid, the 2026 default for AI SaaS:
- **Freemium** — watchlists, delayed data, limited agent runs/month → acquisition.
- **Pro subscription** (~$20–50/mo) — unlimited research, real-time data,
  journaling/analytics, alerts, broker read-sync.
- **Usage credits for agent runs** — each LLM research run has real token cost;
  meter heavy users with credits on top of the base tier (aligns price with cost).
- **RIA / white-label tier** (B2B2C) — multi-client seats, audit export,
  compliance reporting. Highest ARPU; your audit/guardrail design is the selling
  point.

Subscriptions (not per-trade fees) align your incentives with *user success*,
not trading frequency — itself a trust message.

## The 90-day shape

- **Weeks 1–3:** correctness/safety tests + CI floor; auth + multi-tenant data.
- **Weeks 4–7:** broker read-only sync; performance/behavioral journaling MVP;
  compliance/disclaimer layer.
- **Weeks 8–12:** NL intent front-door; mobile push approvals; freemium/paywall
  + billing. Private beta with active retail traders.

## Sources

- [Robinhood launches agentic AI trading (TheStreet)](https://www.thestreet.com/investing/stocks/robinhood-hood-stock-ceo-launches-bold-agentic-ai-trading-feature)
- [Bloomberg embeds agentic AI into the Terminal (The TRADE)](https://www.thetradenews.com/bloomberg-embeds-agentic-ai-into-the-terminal/)
- [Top AI trading tools 2026 (Pragmatic Coders)](https://www.pragmaticcoders.com/blog/top-ai-tools-for-traders)
- [How AI is changing how retail traders analyze performance (BreakingAC)](https://breakingac.com/news/2026/may/11/how-ai-is-quietly-changing-the-way-retail-traders-analyze-their-performance/)
- [Will AI trading make markets harder for retail in 2026? (Bookmap)](https://bookmap.com/blog/will-ai-trading-make-markets-harder-for-retail-in-2026)
- [The "Glass Box" Copilot — human-in-the-loop standard (Dualboot Partners)](https://www.dualbootpartners.com/insights/the-glass-box-copilot/)
- [AI compliance for RIAs in 2026 (Ncontracts)](https://www.ncontracts.com/nsight-blog/investment-advisers-artificial-intelligence)
- [SEC: AI and the future of investment management](https://www.sec.gov/newsroom/speeches-statements/daly-020326-artificial-intelligence-future-investment-management)
- [FINRA 2026 Annual Regulatory Oversight Report (AI section)](https://www.finra.org/sites/default/files/2025-12/2026-annual-regulatory-oversight-report.pdf)
- [Monetize trading apps: 2026 revenue guide](https://www.mobileappdevelopmentcompany.us/blog/monetize-your-mobile-trading-app/)
- [The 2026 guide to SaaS, AI, and agentic pricing (Monetizely)](https://www.getmonetizely.com/blogs/the-2026-guide-to-saas-ai-and-agentic-pricing-models)
