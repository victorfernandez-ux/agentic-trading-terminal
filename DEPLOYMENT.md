# Hosting the terminal on a public URL (Vercel + Render)

The app is two deployables, and only one of them fits Vercel:

| Piece | Where | Why |
|---|---|---|
| `frontend/` (Next.js) | **Vercel** (free Hobby plan) | Static + SSR, exactly what Vercel is for. |
| `backend/` (FastAPI) | **Render** (free plan, Docker) | Needs a long-running process: the `/ws/quotes` WebSocket, background scan/alert loops, and a database. Vercel serverless functions support none of that. |

The frontend reaches the backend two ways, both already configurable:

- HTTP: Next rewrites `/api/*` → `BACKEND_URL` (**build-time** — set it before
  `next build`, changing it later requires a redeploy). See `next.config.mjs`.
- WebSocket: the Watchlist connects straight to `NEXT_PUBLIC_WS_BASE`
  (also build-time). See `components/Watchlist.tsx`.

## 1. Deploy the backend on Render

1. Sign up at https://render.com with your GitHub account (free, no card).
2. New → **Blueprint** → pick this repo. Render reads `render.yaml` and
   creates the `att-backend` Docker service from `backend/Dockerfile`.
3. Fill the prompted env vars:
   - `CORS_ORIGINS` / `PUBLIC_BASE_URL`: your Vercel URL once you have it
     (e.g. `https://agentic-trading-terminal.vercel.app`). You can deploy
     with a placeholder and update after step 2 — env changes restart the
     service automatically.
   - `DATABASE_URL`: `sqlite:////data/terminal.db` for a quick demo
     (**resets on every deploy/restart** — the free plan has no disk), or a
     free hosted Postgres for real persistence: create a project on
     https://neon.tech or https://supabase.com and paste its connection
     string in the form `postgresql+psycopg://user:pass@host/db`.
   - `OPENROUTER_API_KEY`: your key (agents fail without an LLM).
   - `API_TOKEN` is auto-generated — copy it from the service's Environment
     tab; you'll paste it into the UI to sign in.
4. Note the service URL, e.g. `https://att-backend.onrender.com`, and check
   `https://att-backend.onrender.com/health` returns OK.

Free-plan behavior: the service sleeps after ~15 min idle and the next
request takes ~1 min to wake it. Fine for a personal terminal; the paid
tier ($7/mo) removes it.

## 2. Deploy the frontend on Vercel

1. https://vercel.com → Add New → Project → import this GitHub repo.
2. **Root Directory: `frontend`** (Vercel then auto-detects Next.js).
3. Environment variables (both are baked in at build time):
   - `BACKEND_URL` = `https://att-backend.onrender.com`
   - `NEXT_PUBLIC_WS_BASE` = `wss://att-backend.onrender.com`
4. Deploy. Your site is live at `https://<project-name>.vercel.app`.
5. Go back to Render and set `CORS_ORIGINS` and `PUBLIC_BASE_URL` to that
   exact origin (no trailing slash).
6. Open the site, paste the `API_TOKEN` value into the token gate. Done.

If you ever change `BACKEND_URL`/`NEXT_PUBLIC_WS_BASE`, trigger a Vercel
redeploy — they're compiled into the build, not read at runtime.

## 3. Domain

- **Zero-setup free:** the `*.vercel.app` subdomain you got in step 2.
  Rename the Vercel project to pick the word before `.vercel.app`. HTTPS
  included, nothing to configure.
- **Free custom domain — DigitalPlat FreeDomain**
  (https://github.com/DigitalPlatDev/FreeDomain): free registration of
  `yourname.dpdns.org` / `.us.kg` / `.qzz.io` / `.xx.kg` / `.qd.je`.
  DigitalPlat doesn't host DNS records itself — you point the domain at
  custom nameservers, so pair it with a free Cloudflare DNS zone:
  1. Register at https://dash.domain.digitalplat.org/ (account +
     identity/GitHub verification; see their tutorial in the repo).
  2. Add the domain as a site on https://dash.cloudflare.com (Free plan);
     Cloudflare assigns you two nameservers.
  3. In the DigitalPlat dashboard, set the domain's nameservers to those
     two Cloudflare nameservers.
  4. In Vercel → Project → Settings → Domains, add the domain; Vercel shows
     the record it wants — create it in Cloudflare (CNAME →
     `cname.vercel-dns.com`, **DNS-only / grey cloud**, not proxied, so
     Vercel can issue its TLS cert).
  5. Update `CORS_ORIGINS` and `PUBLIC_BASE_URL` on Render to the new
     origin (e.g. `https://yourname.dpdns.org`).
  Caveat: it's a registrar-style free service run by a community project —
  fine for a personal terminal, but don't hang anything business-critical
  on it, and note their renewal rules so the domain doesn't lapse.
- **Nearly free, most robust:** a `.xyz`/`.site` domain is $1–3/yr at
  Porkbun or Cloudflare Registrar; same Vercel + DNS steps as above.
- Other community options: https://is-a.dev gives `you.is-a.dev` via a
  GitHub PR and also works with Vercel.

## Security checklist before sharing the URL

- `API_TOKEN` set (Render blueprint generates it) — without it the API is
  open to the internet.
- `CORS_ORIGINS` locked to your exact frontend origin.
- Trading stays paper-only and human-approved (`TRADING_MODE=paper`,
  `REQUIRE_HUMAN_APPROVAL=true` are the defaults — don't override them).
- Keep provider/LLM keys only in Render's env vars, never in the repo.
