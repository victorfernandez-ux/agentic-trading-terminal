"use client";

/**
 * Fear & Greed dial — CNN-style semicircle gauge with a Stock Market / Crypto
 * toggle. Stocks come from CNN (keyless composite fallback if CNN is
 * unreachable); crypto from alternative.me. Sentiment is context — it never
 * trades. Refreshes every 5 minutes; the backend caches for 10.
 */

import { useState } from "react";
import type { FearGreedReading as FG } from "@/lib/types";
import { usePolledFetch } from "@/lib/usePolledFetch";

// Five sentiment bands, drawn left→right across the dial.
const BANDS = [
  { from: 0, to: 25, color: "#f7768e" },   // Extreme Fear
  { from: 25, to: 45, color: "#ff9e64" },  // Fear
  { from: 45, to: 55, color: "#e0af68" },  // Neutral
  { from: 55, to: 75, color: "#9ece6a" },  // Greed
  { from: 75, to: 100, color: "#73daca" }, // Extreme Greed
];

function bandColor(v: number): string {
  return (BANDS.find((b) => v < b.to) ?? BANDS[BANDS.length - 1]).color;
}

// Polar→cartesian on a 180° arc. value 0→100 maps to angle 180°(left)→0°(right).
function pointOnArc(cx: number, cy: number, r: number, value: number) {
  const angle = Math.PI * (1 - Math.max(0, Math.min(100, value)) / 100);
  return { x: cx + r * Math.cos(angle), y: cy - r * Math.sin(angle) };
}

function arcPath(cx: number, cy: number, r: number, from: number, to: number) {
  const a = pointOnArc(cx, cy, r, from);
  const b = pointOnArc(cx, cy, r, to);
  // always the minor arc on a semicircle → large-arc flag 0, sweep 1
  return `M ${a.x} ${a.y} A ${r} ${r} 0 0 1 ${b.x} ${b.y}`;
}

function Dial({ data }: { data: FG | null }) {
  const W = 240;
  const H = 150;
  const cx = W / 2;
  const cy = 130;
  const r = 92;
  const stroke = 16;

  const v = data?.value;
  const hasValue = typeof v === "number";
  const color = hasValue ? bandColor(v as number) : "#5c6773";
  const needle = pointOnArc(cx, cy, r - 6, hasValue ? (v as number) : 50);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      {/* colored band arcs */}
      {BANDS.map((b) => (
        <path
          key={b.from}
          d={arcPath(cx, cy, r, b.from + 0.6, b.to - 0.6)}
          fill="none"
          stroke={b.color}
          strokeWidth={stroke}
          strokeLinecap="round"
          opacity={hasValue ? 1 : 0.25}
        />
      ))}

      {hasValue && (
        <>
          {/* needle */}
          <line
            x1={cx}
            y1={cy}
            x2={needle.x}
            y2={needle.y}
            stroke="#e6edf3"
            strokeWidth={3}
            strokeLinecap="round"
          />
          <circle cx={cx} cy={cy} r={6} fill={color} />
          {/* value + label */}
          <text x={cx} y={cy - 30} textAnchor="middle" fontSize={30} fontWeight={700} fill="#e6edf3">
            {Math.round(v as number)}
          </text>
          <text x={cx} y={cy - 12} textAnchor="middle" fontSize={12} fontWeight={600} fill={color}>
            {data?.label}
          </text>
        </>
      )}

      {!hasValue && (
        <text x={cx} y={cy - 18} textAnchor="middle" fontSize={12} fill="#5c6773">
          {data?.error ? "unavailable" : "loading…"}
        </text>
      )}
    </svg>
  );
}

function useFearGreed(market: "stocks" | "crypto"): FG | null {
  const { data, error } = usePolledFetch<FG>(
    `/api/analytics/sentiment/fear-greed?market=${market}`,
    300_000,
  );
  // error WINS over kept data: a pre-outage sentiment reading shown as
  // current is worse than "unavailable" (review finding — the old code
  // degraded the dial on every failed refresh; preserve that).
  if (error) return { market, error: "offline" };
  return data;
}

/** embedded=true (desktop): renders inside the Watchlist panel with its own
 *  divider + title. embedded=false (mobile): the page wraps it in a panel
 *  that already provides the title — rendering our own duplicated it. */
export default function FearGreed({ embedded = true }: { embedded?: boolean }) {
  const [market, setMarket] = useState<"stocks" | "crypto">("stocks");
  const stocks = useFearGreed("stocks");
  const crypto = useFearGreed("crypto");

  const active = market === "stocks" ? stocks : crypto;

  const tab = (key: "stocks" | "crypto", label: string) => (
    <button
      onClick={() => setMarket(key)}
      style={{
        flex: 1,
        padding: "5px 8px",
        fontSize: 11,
        cursor: "pointer",
        border: "none",
        borderRadius: 5,
        background: market === key ? "#2a3140" : "transparent",
        color: market === key ? "#e6edf3" : "#9aa5b1",
        fontWeight: market === key ? 600 : 400,
      }}
    >
      {label}
    </button>
  );

  return (
    <div style={embedded ? { marginTop: 16, borderTop: "1px solid #1c2330", paddingTop: 12 } : undefined}>
      {embedded && <h2 className="panel-title">Fear &amp; Greed</h2>}
      <div
        style={{
          display: "flex",
          gap: 4,
          padding: 3,
          borderRadius: 7,
          background: "#161b25",
          marginBottom: 6,
        }}
      >
        {tab("stocks", "Stock Market")}
        {tab("crypto", "Crypto")}
      </div>
      <Dial data={active} />
      <div style={{ textAlign: "right", fontSize: 10, color: "#5c6773", marginTop: -4 }}>
        {active?.source && `source: ${active.source}`}
      </div>
    </div>
  );
}
