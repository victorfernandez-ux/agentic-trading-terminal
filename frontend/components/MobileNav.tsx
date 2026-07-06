"use client";

export type MobileTab = "markets" | "chart" | "agent" | "orders" | "analytics";

// ︎ forces text-style rendering so icons stay monochrome on iOS.
export const MOBILE_TABS: { id: MobileTab; icon: string; label: string }[] = [
  { id: "markets", icon: "☰", label: "Markets" },
  { id: "chart", icon: "∿", label: "Chart" },
  { id: "agent", icon: "⚙︎", label: "Agent" },
  { id: "orders", icon: "✓", label: "Orders" },
  { id: "analytics", icon: "Σ", label: "Analytics" },
];

/** Fixed bottom tab bar for the mobile shell (styles in globals.css). */
export default function MobileNav({
  tab,
  onSelect,
}: {
  tab: MobileTab;
  onSelect: (t: MobileTab) => void;
}) {
  return (
    <nav className="m-nav" aria-label="Primary">
      {MOBILE_TABS.map((t) => (
        <button
          key={t.id}
          className={tab === t.id ? "active" : undefined}
          onClick={() => onSelect(t.id)}
          aria-current={tab === t.id ? "page" : undefined}
        >
          <span className="icon" aria-hidden>
            {t.icon}
          </span>
          {t.label}
        </button>
      ))}
    </nav>
  );
}
