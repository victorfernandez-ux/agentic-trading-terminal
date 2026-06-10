"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, type IChartApi } from "lightweight-charts";

type Bar = { t: number | string; o: number; h: number; l: number; c: number; v: number };

/** Live candlestick chart backed by /api/market/bars/{symbol}. */
export default function PriceChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [status, setStatus] = useState("loading…");

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
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

    const onResize = () =>
      chart.applyOptions({ width: containerRef.current?.clientWidth ?? 600 });
    onResize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); chart.remove(); };
  }, [symbol]);

  return (
    <div>
      <div style={{ fontSize: 11, color: "#5c6773", marginBottom: 6 }}>
        {symbol} · {status}
      </div>
      <div ref={containerRef} />
    </div>
  );
}
