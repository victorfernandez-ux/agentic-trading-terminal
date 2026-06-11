"use client";

/**
 * Global symbol search (Yahoo search proxied by /api/market/search):
 * equities on 40+ exchanges, ETFs, crypto, FX (=X), indices (^), futures (=F).
 * Debounced dropdown; Enter or click adds to the watchlist.
 */

import { useEffect, useRef, useState } from "react";

type Hit = { symbol: string; name: string; exchange: string; type: string };

export default function SymbolSearch({ onAdd }: { onAdd: (symbol: string) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setHits([]);
      setOpen(false);
      return;
    }
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const r = await fetch(`/api/market/search?q=${encodeURIComponent(q.trim())}&limit=8`);
        const j = await r.json();
        setHits(j.results ?? []);
        setOpen(true);
      } catch {
        setHits([]);
      } finally {
        setBusy(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (sym: string) => {
    onAdd(sym);
    setQ("");
    setHits([]);
    setOpen(false);
  };

  return (
    <div ref={boxRef} style={{ position: "relative", marginBottom: 8 }}>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && hits[0]) pick(hits[0].symbol);
          if (e.key === "Escape") setOpen(false);
        }}
        onFocus={() => hits.length && setOpen(true)}
        placeholder={busy ? "searching…" : "search any market…"}
        style={{
          width: "100%",
          boxSizing: "border-box",
          background: "#0b0e14",
          color: "#d6deeb",
          border: "1px solid #1c2330",
          borderRadius: 6,
          padding: "6px 8px",
          fontSize: 12,
          fontFamily: "inherit",
        }}
      />
      {open && hits.length > 0 && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 30,
            background: "#10141f",
            border: "1px solid #1c2330",
            borderRadius: 6,
            marginTop: 4,
            maxHeight: 260,
            overflow: "auto",
            boxShadow: "0 8px 24px #000a",
          }}
        >
          {hits.map((h) => (
            <button
              key={h.symbol}
              onClick={() => pick(h.symbol)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                background: "transparent",
                border: "none",
                borderBottom: "1px solid #161c2a",
                color: "#d6deeb",
                padding: "6px 8px",
                cursor: "pointer",
                fontFamily: "inherit",
                fontSize: 11,
              }}
            >
              <b style={{ color: "#7aa2f7" }}>{h.symbol}</b>{" "}
              <span style={{ color: "#9aa5b1" }}>{h.name}</span>
              <span style={{ float: "right", color: "#5c6773" }}>
                {h.exchange} · {h.type}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
