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
import useIsMobile from "@/lib/useIsMobile";

type Health = { status: string; trading_mode: string; require_human_approval: boolean };

// Theme values come from the :root variables in globals.css so the desktop
// grid and the mobile .m-panel class can't drift apart.
const panel: React.CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: 16,
  background: "var(--panel)",
  overflow: "auto",
};

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
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setErr("backend offline — start uvicorn on :8000"));
  }, []);

  const bump = () => setRefreshKey((k) => k + 1);

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
    approval: <ApprovalQueue refreshKey={refreshKey} onChange={bump} />,
    positions: <Positions refreshKey={refreshKey} />,
    analytics: <Analytics symbol={symbol} onSelect={addSymbol} />,
    news: <News symbol={symbol} />,
    alerts: <Alerts symbol={symbol} />,
    fearGreed: <FearGreed />,
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

        <div className={view("markets")}>
          {/* overflow visible: .m-panel's overflow-x:auto would turn the
              panel into a scroll container and clip the search dropdown. */}
          <section className="m-panel" style={{ overflow: "visible" }}>
            <h2 style={h2}>Watchlist</h2>
            {panels.search}
            <Watchlist
              symbols={watch}
              selected={symbol}
              onSelect={(s) => { setSymbol(s); setTab("chart"); }}
              onQuotes={setQuotes}
              onRemove={removeSymbol}
            />
          </section>
          <section className="m-panel">
            <h2 style={h2}>Fear &amp; Greed</h2>
            {panels.fearGreed}
          </section>
        </div>

        <div className={view("chart")}>
          <section className="m-panel">
            <h2 style={h2}>Chart</h2>
            {panels.chart}
          </section>
          <section className="m-panel">
            <h2 style={h2}>News — {symbol}</h2>
            {panels.news}
          </section>
        </div>

        <div className={view("agent")}>
          <section className="m-panel">
            <h2 style={h2}>Agent Console — {symbol}</h2>
            {panels.agent}
          </section>
        </div>

        <div className={view("orders")}>
          <section className="m-panel">
            <h2 style={h2}>Approval Queue</h2>
            {panels.approval}
          </section>
          <section className="m-panel">
            <h2 style={h2}>Positions &amp; P&amp;L</h2>
            {panels.positions}
          </section>
          <section className="m-panel">
            <h2 style={h2}>Alerts</h2>
            {panels.alerts}
          </section>
        </div>

        <div className={view("analytics")}>
          <section className="m-panel">
            <h2 style={h2}>Analytics — {symbol}</h2>
            {panels.analytics}
          </section>
        </div>

        <MobileNav tab={tab} onSelect={setTab} />
      </main>
    );
  }

  return (
    <main style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: 18, margin: 0 }}>⚡ Agentic Trading Terminal</h1>
        <span style={{ fontSize: 12, color: healthColor }}>{healthLine}</span>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "200px 1.3fr 340px",
          gridTemplateRows: "minmax(320px, auto) auto auto auto",
          gridTemplateAreas: `"watch chart approval" "watch agents positions" "watch analytics news" "watch alerts alerts"`,
          gap: 16,
        }}
      >
        <section style={{ ...panel, gridArea: "watch" }}>
          <h2 style={h2}>Watchlist</h2>
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

        <section style={{ ...panel, gridArea: "chart" }}>
          <h2 style={h2}>Chart</h2>
          {panels.chart}
        </section>

        <section style={{ ...panel, gridArea: "agents" }}>
          <h2 style={h2}>Agent Console</h2>
          {panels.agent}
        </section>

        <section style={{ ...panel, gridArea: "approval" }}>
          <h2 style={h2}>Approval Queue</h2>
          {panels.approval}
        </section>

        <section style={{ ...panel, gridArea: "positions" }}>
          <h2 style={h2}>Positions &amp; P&amp;L</h2>
          {panels.positions}
        </section>

        <section style={{ ...panel, gridArea: "analytics" }}>
          <h2 style={h2}>Analytics</h2>
          {panels.analytics}
        </section>

        <section style={{ ...panel, gridArea: "news", maxHeight: 420 }}>
          <h2 style={h2}>News — {symbol}</h2>
          {panels.news}
        </section>

        <section style={{ ...panel, gridArea: "alerts" }}>
          <h2 style={h2}>Alerts</h2>
          {panels.alerts}
        </section>
      </div>
    </main>
  );
}

const h2: React.CSSProperties = { fontSize: 13, margin: "0 0 10px", color: "var(--accent)" };
