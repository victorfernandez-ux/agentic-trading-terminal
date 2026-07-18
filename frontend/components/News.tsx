"use client";

/**
 * Per-symbol headlines (Yahoo RSS via /api/market/news). The same items the
 * research agent reads as evidence — what the human sees is what the agent saw.
 */

import type { NewsItem } from "@/lib/types";
import { usePolledFetch } from "@/lib/usePolledFetch";

function ago(ts: number | null): string {
  if (!ts) return "";
  const m = Math.max(0, Math.round((Date.now() - ts) / 60000));
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h}h` : `${Math.round(h / 24)}d`;
}

type NewsPayload = { items: NewsItem[]; err: string | null };

export default function News({ symbol }: { symbol: string }) {
  const { data, error: fetchErr } = usePolledFetch<NewsPayload>(
    `/api/market/news?symbol=${encodeURIComponent(symbol)}&limit=12`,
    5 * 60_000,
    {
      resetOnUrlChange: true,
      parse: (raw) => {
        const j = raw as { items?: NewsItem[]; error?: unknown };
        // j.error is a string from /market/news, but a {code, message}
        // envelope on auth/HTTP errors — never render an object as JSX.
        return {
          items: j.items ?? [],
          err: typeof j.error === "string" ? j.error : j.error ? "unavailable" : null,
        };
      },
    },
  );
  const items = data?.items ?? [];
  const err = data?.err ?? (fetchErr ? "news unavailable" : null);

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
