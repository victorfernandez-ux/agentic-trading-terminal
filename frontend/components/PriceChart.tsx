"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, type IChartApi } from "lightweight-charts";
import type { Quote } from "@/components/Watchlist";
import { observeChartWidth } from "@/lib/chartWidth";

type Bar = { t: number | string; o: number; h: number; l: number; c: number; v: number };

/** Live candlestick chart backed by /api/market/bars/{symbol}.
 *  Header shows the streaming price/% change when a live quote is supplied. */
export default function PriceChart({ symbol, liveQuote }: { symbol: string; liveQuote?: Quote }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [status, setStatus] = useState("loading…");

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      height: 260,
      layout: { background: { color: "transparent" }, textColor: "#7aa2f7" },
      grid: { vertLines: { color: "#1c2330" }, horzLines: { color: "#1c2330" } },
      timeScale: { borderColor: "#1c2330" },
      rightPriceScale: { borderColor: "#1c2330" },
    });
    chartRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: "#8fd694", downColor: "#f7768e",
      wickUpColor: "#8fd694", wickDownColor: "#f7768e", borderVisible: false,
    });

    const enc = encodeURIComponent(symbol);
    fetch(`/api/market/bars?symbol=${enc}&timeframe=1D&limit=120`)
      .then((r) => r.json())
      .then((data) => {
        const bars: Bar[] = data.bars ?? [];
        if (!bars.length) { setStatus(`no data (provider: ${data.provider})`); return; }
        const candles = bars
          .map((b) => ({
            time: Math.floor(Number(b.t) / 1000) as never,
            open: b.o, high: b.h, low: b.l, close: b.c,
          }))
          .sort((a, b) => (a.time as number) - (b.time as number));
        series.setData(candles);
        chart.timeScale().fitContent();
        setStatus(`${bars.length} bars · ${data.provider}`);
      })
      .catch(() => setStatus("backend offline"));

    const unobserve = observeChartWidth(el, chart);
    return () => { unobserve(); chart.remove(); };
  }, [symbol]);

  const up = (liveQuote?.pct_change ?? 0) >= 0;
  return (
    <div>
      <div style={{ fontSize: 11, color: "#5c6773", marginBottom: 6, display: "flex", gap: 10 }}>
        <span style={{ color: "#d6deeb" }}>{symbol}</span>
        {liveQuote?.price != null && (
          <span style={{ color: "#d6deeb" }}>
            {liveQuote.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            {liveQuote.pct_change != null && (
              <span style={{ color: up ? "#8fd694" : "#f7768e", marginLeft: 6 }}>
                {up ? "+" : ""}
                {liveQuote.pct_change.toFixed(2)}%
              </span>
            )}
          </span>
        )}
        <span>· {status}</span>
      </div>
      <div ref={containerRef} />
    </div>
  );
}
