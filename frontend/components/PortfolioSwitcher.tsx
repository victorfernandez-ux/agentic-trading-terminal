"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Portfolio = { id: string; name: string };

// Selecting "default" preserves the pre-portfolio view (no filter, all
// orders/positions) — other portfolios filter the queue and positions.
export default function PortfolioSwitcher({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);

  useEffect(() => {
    apiFetch("/api/portfolios")
      .then((r) => r.json())
      .then((d) => setPortfolios(Array.isArray(d?.portfolios) ? d.portfolios : []))
      .catch(() => setPortfolios([]));
  }, []);

  // With only the seeded default there is nothing to switch — hide.
  if (portfolios.length < 2) return null;

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      title="Portfolio"
      style={{
        background: "var(--bg)",
        color: "var(--text)",
        border: "1px solid var(--border)",
        borderRadius: 6,
        padding: "2px 6px",
        fontFamily: "inherit",
        fontSize: 11,
      }}
    >
      {portfolios.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  );
}
