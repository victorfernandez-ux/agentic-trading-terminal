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

type Health = { status: string; trading_mode: string; require_human_approval: boolean };

const DEFAULT_WATCH = ["BTC/USD", "ETH/USD", "SOL/USD", "AAPL", "NVDA", "SPY"];
const WATCH_KEY = "att.watchlist.v1";

export default function Terminal() {
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

      <div className="terminal-grid">
        <section className="panel" style={{ gridArea: "watch" }}>
          <h2 className="panel-title">Watchlist</h2>
          <SymbolSearch onAdd={addSymbol} />
          <Watchlist
            symbols={watch}
            selected={symbol}
            onSelect={setSymbol}
            onQuotes={setQuotes}
            onRemove={removeSymbol}
          />
          <FearGreed />
        </section>

        <section className="panel" style={{ gridArea: "chart" }}>
          <h2 className="panel-title">
            Chart <span className="title-meta">{symbol}</span>
          </h2>
          <PriceChart symbol={symbol} liveQuote={quotes[symbol]} />
        </section>

        <section className="panel" style={{ gridArea: "agents" }}>
          <h2 className="panel-title">Agent Console</h2>
          <AgentConsole symbol={symbol} onProposed={bump} />
        </section>

        <section className="panel" style={{ gridArea: "approval" }}>
          <h2 className="panel-title">Approval Queue</h2>
          <ApprovalQueue refreshKey={refreshKey} onChange={bump} />
        </section>

        <section className="panel" style={{ gridArea: "positions" }}>
          <h2 className="panel-title">Positions &amp; P&amp;L</h2>
          <Positions refreshKey={refreshKey} />
        </section>

        <section className="panel" style={{ gridArea: "analytics" }}>
          <h2 className="panel-title">Analytics</h2>
          <Analytics symbol={symbol} onSelect={addSymbol} />
        </section>

        <section className="panel" style={{ gridArea: "news", maxHeight: 420 }}>
          <h2 className="panel-title">
            News <span className="title-meta">{symbol}</span>
          </h2>
          <News symbol={symbol} />
        </section>

        <section className="panel" style={{ gridArea: "alerts" }}>
          <h2 className="panel-title">Alerts</h2>
          <Alerts symbol={symbol} />
        </section>
      </div>
    </main>
  );
}
