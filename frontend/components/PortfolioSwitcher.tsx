"use client";

import type { Portfolio } from "@/lib/types";
import { usePolledFetch } from "@/lib/usePolledFetch";

// Selecting "default" preserves the pre-portfolio view (no filter, all
// orders/positions) — other portfolios filter the queue and positions.
export default function PortfolioSwitcher({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  const { data } = usePolledFetch<Portfolio[]>("/api/portfolios", 0, {
    parse: (d) => {
      const list = (d as { portfolios?: unknown })?.portfolios;
      return Array.isArray(list) ? (list as Portfolio[]) : [];
    },
  });
  const portfolios = data ?? [];

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
