"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Order = {
  id: string;
  symbol: string;
  side: string;
  qty: number;
  order_type: string;
  status: string;
  est_notional?: number;
  est_price?: number;
  source?: string;
  broker_result?: { status?: string; broker?: string };
};

const STATUS_COLOR: Record<string, string> = {
  PENDING_APPROVAL: "#e0af68",
  SUBMITTED: "#8fd694",
  REJECTED: "#f7768e",
};

export default function ApprovalQueue({ refreshKey, onChange }: { refreshKey: number; onChange?: () => void }) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch("/api/orders")
      .then((r) => r.json())
      .then(setOrders)
      .catch(() => setOrders([]));
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  async function act(id: string, action: "approve" | "reject") {
    setBusy(id);
    try {
      await apiFetch(`/api/orders/${id}/${action}`, { method: "POST" });
      load();
      onChange?.(); // refresh positions after a fill
    } finally {
      setBusy(null);
    }
  }

  if (!orders.length) {
    return (
      <p style={{ fontSize: 12, color: "#5c6773" }}>
        No orders yet. Run the agents — proposed trades land here for your approval.
      </p>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {orders.map((o) => (
        <div key={o.id} style={{ border: "1px solid #1c2330", borderRadius: 6, padding: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
            <span style={{ color: "#d6deeb" }}>
              <b style={{ textTransform: "uppercase", color: o.side === "buy" ? "#8fd694" : "#f7768e" }}>
                {o.side}
              </b>{" "}
              {o.qty} {o.symbol}
              {o.est_notional ? ` · ~$${o.est_notional}` : ""}
            </span>
            <span style={{ color: STATUS_COLOR[o.status] ?? "#9aa5b1" }}>{o.status}</span>
          </div>
          <div style={{ fontSize: 10, color: "#5c6773", margin: "2px 0 6px" }}>
            {o.id} · {o.order_type} · {o.source ?? "human"}
            {o.broker_result?.status ? ` · ${o.broker_result.status}` : ""}
          </div>
          {o.status === "PENDING_APPROVAL" && (
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={() => act(o.id, "approve")} disabled={busy === o.id} style={ok}>
                Approve
              </button>
              <button onClick={() => act(o.id, "reject")} disabled={busy === o.id} style={no}>
                Reject
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

const base: React.CSSProperties = {
  padding: "4px 10px",
  borderRadius: 5,
  fontSize: 12,
  cursor: "pointer",
  fontFamily: "inherit",
  border: "1px solid",
};
const ok: React.CSSProperties = { ...base, borderColor: "#2e6b3a", background: "#16301d", color: "#8fd694" };
const no: React.CSSProperties = { ...base, borderColor: "#6b2e34", background: "#301619", color: "#f7768e" };
