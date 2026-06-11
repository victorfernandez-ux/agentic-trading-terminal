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

type Health = { status: string; trading_mode: string; require_human_approval: boolean };

const panel: React.CSSProperties = {
  border: "1px solid #1c2330",
  borderRadius: 8,
  padding: 16,
  background: "#0f1320",
  overflow: "auto",
};

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
    <main style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ fontSize: 18, margin: 0 }}>⚡ Agentic Trading Terminal</h1>
        <span style={{ fontSize: 12, color: health ? "#8fd694" : "#e0af68" }}>
          {health
            ? `● ${health.status} · mode: ${health.trading_mode} · approval: ${
                health.require_human_approval ? "required" : "off"
              }`
            : err ?? "connecting…"}
        </span>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "200px 1.3fr 340px",
          gridTemplateRows: "minmax(320px, auto) auto auto",
          gridTemplateAreas: `"watch chart approval" "watch agents positions" "watch analytics news"`,
          gap: 16,
        }}
      >
        <section style={{ ...panel, gridArea: "watch" }}>
          <h2 style={h2}>Watchlist</h2>
          <SymbolSearch onAdd={addSymbol} />
          <Watchlist
            symbols={watch}
            selected={symbol}
            onSelect={setSymbol}
            onQuotes={setQuotes}
            onRemove={removeSymbol}
          />
        </section>

        <section style={{ ...panel, gridArea: "chart" }}>
          <h2 style={h2}>Chart</h2>
          <PriceChart symbol={symbol} liveQuote={quotes[symbol]} />
        </section>

        <section style={{ ...panel, gridArea: "agents" }}>
          <h2 style={h2}>Agent Console</h2>
          <AgentConsole symbol={symbol} onProposed={bump} />
        </section>

        <section style={{ ...panel, gridArea: "approval" }}>
          <h2 style={h2}>Approval Queue</h2>
          <ApprovalQueue refreshKey={refreshKey} onChange={bump} />
        </section>

        <section style={{ ...panel, gridArea: "positions" }}>
          <h2 style={h2}>Positions &amp; P&amp;L</h2>
          <Positions refreshKey={refreshKey} />
        </section>

        <section style={{ ...panel, gridArea: "analytics" }}>
          <h2 style={h2}>Analytics</h2>
          <Analytics symbol={symbol} onSelect={addSymbol} />
        </section>

        <section style={{ ...panel, gridArea: "news", maxHeight: 420 }}>
          <h2 style={h2}>News — {symbol}</h2>
          <News symbol={symbol} />
        </section>
      </div>
    </main>
  );
}

const h2: React.CSSProperties = { fontSize: 13, margin: "0 0 10px", color: "#7aa2f7" };
