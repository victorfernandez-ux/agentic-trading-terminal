"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch, tokenized } from "@/lib/api";

export type Quote = {
  symbol: string;
  price: number | null;
  pct_change: number | null;
  provider?: string;
  error?: string;
};

type Props = {
  symbols: string[];
  selected: string;
  onSelect: (s: string) => void;
  onQuotes?: (quotes: Record<string, Quote>) => void; // lets the chart header share live data
  onRemove?: (s: string) => void;
};

/**
 * Live watchlist: streams quotes over /ws/quotes (every few seconds) and
 * falls back to polling REST /api/market/quote if the socket can't connect.
 */
export default function Watchlist({ symbols, selected, onSelect, onQuotes, onRemove }: Props) {
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [mode, setMode] = useState<"connecting" | "live" | "poll">("connecting");
  const onQuotesRef = useRef(onQuotes);
  onQuotesRef.current = onQuotes;

  // Share live quotes with the parent AFTER commit, never inside the setState
  // updater below (calling a parent setter mid-render trips React's
  // "Cannot update a component while rendering a different component").
  useEffect(() => {
    onQuotesRef.current?.(quotes);
  }, [quotes]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    const apply = (list: Quote[]) =>
      setQuotes((prev) => {
        const next = { ...prev };
        for (const q of list) if (q && q.symbol) next[q.symbol] = q;
        return next;  // pure updater; parent is notified via the effect above
      });

    // REST fallback: same payload shape, just slower.
    const startPolling = () => {
      if (pollTimer || disposed) return;
      setMode("poll");
      const poll = async () => {
        const results = await Promise.all(
          symbols.map(async (s) => {
            try {
              const r = await apiFetch(`/api/market/quote?symbol=${encodeURIComponent(s)}`);
              return (await r.json()) as Quote;
            } catch {
              return { symbol: s, price: null, pct_change: null } as Quote;
            }
          })
        );
        if (!disposed) apply(results);
      };
      poll();
      pollTimer = setInterval(poll, 10_000);
    };

    const connect = () => {
      if (disposed) return;
      try {
        // Talk to the backend directly (Next's /api rewrite is HTTP-only).
        // NEXT_PUBLIC_WS_BASE overrides for phones/PWA installs that can't
        // reach the backend on the page host's :8000 (e.g. wss://api.example.com).
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        // || (not ??): an empty-string env value must fall through too.
        const base =
          process.env.NEXT_PUBLIC_WS_BASE || `${proto}://${window.location.hostname}:8000`;
        const qs = encodeURIComponent(symbols.join(","));
        ws = new WebSocket(tokenized(`${base}/ws/quotes?symbols=${qs}`));
        ws.onopen = () => {
          if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
          setMode("live");
        };
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "quotes") apply(msg.quotes);
          } catch { /* ignore malformed frame */ }
        };
        ws.onclose = () => {
          if (disposed) return;
          startPolling(); // keep data flowing…
          retryTimer = setTimeout(connect, 15_000); // …and retry the socket
        };
        ws.onerror = () => ws?.close();
      } catch {
        startPolling();
      }
    };

    connect();
    return () => {
      disposed = true;
      ws?.close();
      if (pollTimer) clearInterval(pollTimer);
      if (retryTimer) clearTimeout(retryTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbols.join(",")]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ fontSize: 10, color: mode === "live" ? "#8fd694" : "#5c6773", marginBottom: 2 }}>
        {mode === "live" ? "● live" : mode === "poll" ? "◌ polling (REST fallback)" : "connecting…"}
      </div>
      {symbols.map((s) => {
        const q = quotes[s];
        const up = (q?.pct_change ?? 0) >= 0;
        return (
          <button
            key={s}
            onClick={() => onSelect(s)}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              gap: 6,
              padding: "6px 8px",
              borderRadius: 6,
              border: "1px solid #1c2330",
              background: s === selected ? "#1a2030" : "transparent",
              color: s === selected ? "#7aa2f7" : "#d6deeb",
              cursor: "pointer",
              fontFamily: "inherit",
              fontSize: 13,
            }}
          >
            <span>
              {s}
              {onRemove && (
                <span
                  onClick={(e) => { e.stopPropagation(); onRemove(s); }}
                  title="remove"
                  style={{ marginLeft: 6, color: "#3a4356", cursor: "pointer", fontSize: 11 }}
                >
                  ×
                </span>
              )}
            </span>
            <span style={{ textAlign: "right", fontSize: 11, lineHeight: 1.3 }}>
              <span style={{ display: "block", color: "#d6deeb" }}>
                {q?.price != null ? q.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
              </span>
              <span style={{ display: "block", color: q?.pct_change == null ? "#5c6773" : up ? "#8fd694" : "#f7768e" }}>
                {q?.pct_change != null ? `${up ? "+" : ""}${q.pct_change.toFixed(2)}%` : ""}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
