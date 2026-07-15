"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Position = {
  symbol: string;
  qty: number;
  avg_cost: number;
  last: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
};

export default function Positions({
  refreshKey,
  portfolio = "default",
}: {
  refreshKey: number;
  portfolio?: string;
}) {
  const [rows, setRows] = useState<Position[]>([]);

  // "default" keeps the unfiltered view (legacy orders may predate
  // portfolio stamping); any other portfolio filters server-side.
  const load = useCallback(() => {
    const qs = portfolio !== "default" ? `?portfolio_id=${encodeURIComponent(portfolio)}` : "";
    apiFetch(`/api/orders/positions/all${qs}`)
      .then((r) => r.json())
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]));
  }, [portfolio]);

  // Reload on approval (refreshKey) and poll every 15s for live P&L.
  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load, refreshKey]);

  if (!rows.length) {
    return (
      <p style={{ fontSize: 12, color: "#5c6773" }}>
        No open positions. Approve an order and it appears here with live P&L.
      </p>
    );
  }

  const totalPnl = rows.reduce((s, r) => s + (r.unrealized_pnl ?? 0), 0);

  return (
    <div className="num" style={{ fontSize: 12 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 0.7fr 0.9fr 1fr", gap: 4, color: "#5c6773", paddingBottom: 4 }}>
        <span>Symbol</span><span>Qty</span><span>Avg→Last</span><span style={{ textAlign: "right" }}>uP&L</span>
      </div>
      {rows.map((r) => {
        const up = (r.unrealized_pnl ?? 0) >= 0;
        const color = up ? "#8fd694" : "#f7768e";
        return (
          <div key={r.symbol} className="tr-hover" style={{ display: "grid", gridTemplateColumns: "1fr 0.7fr 0.9fr 1fr", gap: 4, padding: "4px 0", borderTop: "1px solid #1c2330" }}>
            <span style={{ color: "#d6deeb" }}>{r.symbol}</span>
            <span style={{ color: "#9aa5b1" }}>{r.qty}</span>
            <span style={{ color: "#9aa5b1" }}>
              {r.avg_cost} → {r.last ?? "—"}
            </span>
            <span style={{ textAlign: "right", color }}>
              {r.unrealized_pnl == null ? "—" : `${up ? "+" : ""}${r.unrealized_pnl} (${r.unrealized_pnl_pct}%)`}
            </span>
          </div>
        );
      })}
      <div style={{ display: "flex", justifyContent: "space-between", paddingTop: 6, marginTop: 4, borderTop: "1px solid #2a3550", color: "#9aa5b1" }}>
        <span>Total unrealized</span>
        <span style={{ color: totalPnl >= 0 ? "#8fd694" : "#f7768e" }}>
          {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
