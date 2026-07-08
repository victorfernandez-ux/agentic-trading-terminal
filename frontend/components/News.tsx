"use client";

/**
 * Per-symbol headlines (Yahoo RSS via /api/market/news). The same items the
 * research agent reads as evidence — what the human sees is what the agent saw.
 */

import { useEffect, useState } from "react";

type Item = { title: string; link: string; source: string; published_ts: number | null };

function ago(ts: number | null): string {
  if (!ts) return "";
  const m = Math.max(0, Math.round((Date.now() - ts) / 60000));
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h}h` : `${Math.round(h / 24)}d`;
}

export default function News({ symbol }: { symbol: string }) {
  const [items, setItems] = useState<Item[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let dead = false;
    const load = async () => {
      try {
        const r = await fetch(`/api/market/news?symbol=${encodeURIComponent(symbol)}&limit=12`);
        const j = await r.json();
        if (!dead) {
          setItems(j.items ?? []);
          setErr(j.error ?? null);
        }
      } catch {
        if (!dead) setErr("news unavailable");
      }
    };
    setItems([]);
    load();
    const t = setInterval(load, 5 * 60_000);
    return () => {
      dead = true;
      clearInterval(t);
    };
  }, [symbol]);

  if (err && !items.length)
    return <p style={{ fontSize: 12, color: "#5c6773" }}>no headlines — {err}</p>;
  if (!items.length)
    return <p style={{ fontSize: 12, color: "#5c6773" }}>loading headlines…</p>;

  return (
    <div style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      {items.map((it, i) => (
        <a key={i} href={it.link} target="_blank" rel="noreferrer" className="news-item">
          <span className="num" style={{ color: "#5c6773", marginRight: 6 }}>{ago(it.published_ts)}</span>
          <span className="news-title">{it.title}</span>
        </a>
      ))}
    </div>
  );
}
