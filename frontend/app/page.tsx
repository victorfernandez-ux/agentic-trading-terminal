"use client";

import { useEffect, useState } from "react";
import PriceChart from "@/components/PriceChart";
import AgentConsole from "@/components/AgentConsole";
import ApprovalQueue from "@/components/ApprovalQueue";
import Positions from "@/components/Positions";
import Watchlist, { type Quote } from "@/components/Watchlist";
import Analytics from "@/components/Analytics";
import SymbolSearch from "@/components/SymbolSearch";
import News from "@/components/News";
import Alerts from "@/components/Alerts";
import FearGreed from "@/components/FearGreed";
import MobileNav, { type MobileTab } from "@/components/MobileNav";
import PortfolioSwitcher from "@/components/PortfolioSwitcher";
import useIsMobile from "@/lib/useIsMobile";
import { apiFetch, getToken, setToken, UNAUTHORIZED_EVENT } from "@/lib/api";
import type { Health } from "@/lib/types";

const DEFAULT_WATCH = ["BTC/USD", "ETH/USD", "SOL/USD", "AAPL", "NVDA", "SPY"];
const WATCH_KEY = "att.watchlist.v1";

export default function Terminal() {
  const isMobile = useIsMobile();
  const [tab, setTab] = useState<MobileTab>("markets");
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [symbol, setSymbol] = useState("BTC/USD");
  const [refreshKey, setRefreshKey] = useState(0);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [watch, setWatch] = useState<string[]>(DEFAULT_WATCH);
  // Selected portfolio filters ApprovalQueue + Positions; "default"
  // preserves the pre-portfolio (unfiltered) view.
  const [portfolio, setPortfolio] = useState("default");

  // Hydrate the persisted watchlist after mount (avoids SSR mismatch).
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(WATCH_KEY) ?? "[]");
      if (Array.isArray(saved) && saved.length) setWatch(saved.slice(0, 20));
    } catch { /* corrupted storage — keep defaults */ }
  }, []);

  const persist = (list: string[]) => {
    setWatch(list);
    try { localStorage.setItem(WATCH_KEY, JSON.stringify(list)); } catch { /* quota */ }
  };
  const addSymbol = (s: string) => {
    const sym = s.trim().toUpperCase();
    if (!sym) return;
    if (!watch.includes(sym)) persist([...watch, sym].slice(0, 20));
    setSymbol(sym);
  };
  const removeSymbol = (s: string) => {
    const list = watch.filter((x) => x !== s);
    persist(list.length ? list : DEFAULT_WATCH);
    if (symbol === s) setSymbol((list.length ? list : DEFAULT_WATCH)[0]);
  };

  useEffect(() => {
    apiFetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setErr("backend offline — start uvicorn on :8000"));
  }, []);

  // Token gate: any component's apiFetch hitting a 401 (backend has
  // API_TOKEN set) raises this event; we show an unlock input in the header.
  const [needsToken, setNeedsToken] = useState(false);
  useEffect(() => {
    const onUnauthorized = () => setNeedsToken(true);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);
  const unlock = (token: string) => {
    if (!token.trim()) return;
    setToken(token.trim());
    location.reload(); // simplest way to restart every socket/poller with auth
  };

  const bump = () => setRefreshKey((k) => k + 1);

  const tokenGate = needsToken && (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        unlock(new FormData(e.currentTarget).get("token") as string);
      }}
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "10px 12px",
        background: "var(--panel)",
        fontSize: 12,
      }}
    >
      <span style={{ color: "#e0af68" }}>🔒 API token required</span>
      <input
        name="token"
        type="password"
        defaultValue={getToken()}
        placeholder="paste API_TOKEN"
        autoComplete="off"
        style={{
          flex: 1,
          minWidth: 80,
          background: "var(--bg)",
          color: "var(--text)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "6px 8px",
          fontFamily: "inherit",
        }}
      />
      <button
        type="submit"
        style={{
          background: "#1f2a44",
          color: "var(--accent)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "6px 12px",
          cursor: "pointer",
          fontFamily: "inherit",
          fontSize: 12,
        }}
      >
        unlock
      </button>
    </form>
  );

  const healthLine = health
    ? `● ${health.status} · mode: ${health.trading_mode} · approval: ${
        health.require_human_approval ? "required" : "off"
      }`
    : err ?? "connecting…";
  const healthColor = health ? "#8fd694" : "#e0af68";

  // Viewport unknown for one frame after hydration; render nothing rather
  // than mounting the wrong layout (sockets/pollers would start twice).
  if (isMobile === null) return null;

  // Panels shared verbatim by both layouts — declared once so mobile and
  // desktop can't silently drift. Watchlist is deliberately NOT shared:
  // on mobile, selecting a symbol also jumps to the Chart tab.
  const panels = {
    search: <SymbolSearch onAdd={addSymbol} />,
    chart: <PriceChart symbol={symbol} liveQuote={quotes[symbol]} />,
    agent: <AgentConsole symbol={symbol} onProposed={bump} />,
    approval: <ApprovalQueue refreshKey={refreshKey} onChange={bump} portfolio={portfolio} />,
    positions: <Positions refreshKey={refreshKey} portfolio={portfolio} />,
    portfolioSwitcher: <PortfolioSwitcher value={portfolio} onChange={setPortfolio} />,
    analytics: <Analytics symbol={symbol} onSelect={addSymbol} watchlist={watch} />,
    news: <News symbol={symbol} />,
    alerts: <Alerts symbol={symbol} />,
    // Mobile wraps it in a titled panel; embedded mode would duplicate the
    // "Fear & Greed" heading there.
    fearGreed: <FearGreed embedded={!isMobile} />,
  };

  if (isMobile) {
    // One view per bottom tab. Views stay MOUNTED and are hidden with CSS so
    // the quotes websocket, agent SSE stream and pollers survive tab switches.
    const view = (id: MobileTab): string => `m-view${tab === id ? " active" : ""}`;
    return (
      <main className="m-main">
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            gap: 8,
            padding: "4px 2px 10px",
          }}
        >
          <h1 style={{ fontSize: 15, margin: 0, whiteSpace: "nowrap" }}>⚡ Trading Terminal</h1>
          <span
            title={healthLine}
            style={{
              fontSize: 10,
              color: healthColor,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {healthLine}
          </span>
        </header>

        {tokenGate}

        <div className={view("markets")}>
          {/* overflow visible: .panel's overflow:auto would turn the panel
              into a scroll container and clip the search dropdown. */}
          <section className="panel" style={{ overflow: "visible" }}>
            <h2 className="panel-title">Watchlist</h2>
            {panels.search}
            <Watchlist
              symbols={watch}
              selected={symbol}
              onSelect={(s) => { setSymbol(s); setTab("chart"); }}
              onQuotes={setQuotes}
              onRemove={removeSymbol}
            />
          </section>
          <section className="panel">
            <h2 className="panel-title">Fear &amp; Greed</h2>
            {panels.fearGreed}
          </section>
        </div>

        <div className={view("chart")}>
          <section className="panel">
            <h2 className="panel-title">Chart</h2>
            {panels.chart}
          </section>
          <section className="panel">
            <h2 className="panel-title">News — {symbol}</h2>
            {panels.news}
          </section>
        </div>

        <div className={view("agent")}>
          <section className="panel">
            <h2 className="panel-title">Agent Console — {symbol}</h2>
            {panels.agent}
          </section>
        </div>

        <div className={view("orders")}>
          <section className="panel">
            <h2 className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              Approval Queue {panels.portfolioSwitcher}
            </h2>
            {panels.approval}
          </section>
          <section className="panel">
            <h2 className="panel-title">Positions &amp; P&amp;L</h2>
            {panels.positions}
          </section>
          <section className="panel">
            <h2 className="panel-title">Alerts</h2>
            {panels.alerts}
          </section>
        </div>

        <div className={view("analytics")}>
          <section className="panel">
            <h2 className="panel-title">Analytics — {symbol}</h2>
            {panels.analytics}
          </section>
        </div>

        <MobileNav tab={tab} onSelect={setTab} />
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="masthead">
        <div className="brand">
          <h1>
            <span className="bolt">⚡</span> Agentic Trading Terminal
          </h1>
          <span className="brand-sub">agents propose · you approve · paper fills</span>
        </div>
        <span className="status-pill">
          <span className={`status-dot ${health ? "ok" : err ? "err" : "warn"}`} />
          {health
            ? `${health.status} · mode: ${health.trading_mode} · approval: ${
                health.require_human_approval ? "required" : "off"
              }`
            : err ?? "connecting…"}
        </span>
      </header>

      {tokenGate}

      <div className="terminal-grid">
        <section className="panel" style={{ gridArea: "watch" }}>
          <h2 className="panel-title">Watchlist</h2>
          {panels.search}
          <Watchlist
            symbols={watch}
            selected={symbol}
            onSelect={setSymbol}
            onQuotes={setQuotes}
            onRemove={removeSymbol}
          />
          {panels.fearGreed}
        </section>

        <section className="panel" style={{ gridArea: "chart" }}>
          <h2 className="panel-title">
            Chart <span className="title-meta">{symbol}</span>
          </h2>
          {panels.chart}
        </section>

        <section className="panel" style={{ gridArea: "agents" }}>
          <h2 className="panel-title">Agent Console</h2>
          {panels.agent}
        </section>

        <section className="panel" style={{ gridArea: "approval" }}>
          <h2 className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            Approval Queue {panels.portfolioSwitcher}
          </h2>
          {panels.approval}
        </section>

        <section className="panel" style={{ gridArea: "positions" }}>
          <h2 className="panel-title">Positions &amp; P&amp;L</h2>
          {panels.positions}
        </section>

        <section className="panel" style={{ gridArea: "analytics" }}>
          <h2 className="panel-title">Analytics</h2>
          {panels.analytics}
        </section>

        <section className="panel" style={{ gridArea: "news", maxHeight: 420 }}>
          <h2 className="panel-title">
            News <span className="title-meta">{symbol}</span>
          </h2>
          {panels.news}
        </section>

        <section className="panel" style={{ gridArea: "alerts" }}>
          <h2 className="panel-title">Alerts</h2>
          {panels.alerts}
        </section>
      </div>
    </main>
  );
}
