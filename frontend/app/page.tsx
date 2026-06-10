"use client";

import { useEffect, useState } from "react";
import PriceChart from "@/components/PriceChart";
import AgentConsole from "@/components/AgentConsole";
import ApprovalQueue from "@/components/ApprovalQueue";
import Positions from "@/components/Positions";
import Watchlist, { type Quote } from "@/components/Watchlist";

type Health = { status: string; trading_mode: string; require_human_approval: boolean };

const panel: React.CSSProperties = {
  border: "1px solid #1c2330",
  borderRadius: 8,
  padding: 16,
  background: "#0f1320",
  overflow: "auto",
};

const WATCH = ["BTC/USD", "ETH/USD", "SOL/USD", "AAPL", "NVDA", "SPY"];

export default function Terminal() {
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [symbol, setSymbol] = useState("BTC/USD");
  const [refreshKey, setRefreshKey] = useState(0);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});

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
          gridTemplateRows: "minmax(320px, auto) auto",
          gridTemplateAreas: `"watch chart approval" "watch agents positions"`,
          gap: 16,
        }}
      >
        <section style={{ ...panel, gridArea: "watch" }}>
          <h2 style={h2}>Watchlist</h2>
          <Watchlist symbols={WATCH} selected={symbol} onSelect={setSymbol} onQuotes={setQuotes} />
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
      </div>
    </main>
  );
}

const h2: React.CSSProperties = { fontSize: 13, margin: "0 0 10px", color: "#7aa2f7" };
