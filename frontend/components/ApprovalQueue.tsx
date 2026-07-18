"use client";

import { useEffect, useState } from "react";
import { apiFetch, portfolioQuery } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import type { Order } from "@/lib/types";
import { usePolledFetch } from "@/lib/usePolledFetch";

const STATUS_COLOR: Record<string, string> = {
  PENDING_APPROVAL: "#e0af68",
  SUBMITTED: "#8fd694",
  REJECTED: "#f7768e",
};

/** "proposed 3m ago" — an est_price snapshot ages fast in a moving market. */
function age(ts?: number): string | null {
  const t = timeAgo(ts);
  return t ? `${t} ago` : null;
}

export default function ApprovalQueue({
  refreshKey,
  onChange,
  portfolio = "default",
}: {
  refreshKey: number;
  onChange?: () => void;
  portfolio?: string;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  // Approve is money-shaped: first click arms, second click fires (H2d).
  const [confirming, setConfirming] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Poll (H2b): orders resolved elsewhere (Telegram, MCP, another tab)
  // must disappear here — a stale card invites approving a resolved order.
  // The hook keeps last-known data on a transient failure (`error` banner)
  // instead of blanking to "No orders".
  // resetOnUrlChange: switching portfolios must never leave the previous
  // portfolio's orders rendered (with live Approve buttons) under the new
  // view — blank + banner beats acting on the wrong portfolio.
  const {
    data,
    error: loadErr,
    reload: load,
  } = usePolledFetch<Order[]>(`/api/orders${portfolioQuery(portfolio)}`, 10_000, {
    refreshKey,
    resetOnUrlChange: true,
  });
  const orders = data ?? [];

  // Prune per-order errors for orders that left the list (resolved
  // elsewhere) so a stale message can never attach to a future card.
  useEffect(() => {
    if (!data) return;
    const ids = new Set(data.map((o) => o.id));
    setErrors((prev) => {
      const kept = Object.entries(prev).filter(([id]) => ids.has(id));
      return kept.length === Object.keys(prev).length ? prev : Object.fromEntries(kept);
    });
  }, [data]);

  async function act(id: string, action: "approve" | "reject") {
    setBusy(id);
    setConfirming(null);
    try {
      const r = await apiFetch(`/api/orders/${id}/${action}`, { method: "POST" });
      if (r.ok) {
        setErrors(({ [id]: _cleared, ...rest }) => rest);
      } else {
        // Fail loud (H2a): a 409/500 is not a success. Surface the server's
        // message on the card; the reload below shows the order's real state.
        let msg = `${action} failed (HTTP ${r.status})`;
        try {
          const j = await r.json();
          if (typeof j?.error?.message === "string") msg = `${action} failed: ${j.error.message}`;
        } catch {
          /* keep the status-code message */
        }
        setErrors((e) => ({ ...e, [id]: msg }));
      }
      load();
      onChange?.(); // refresh positions after a fill
    } catch {
      setErrors((e) => ({
        ...e,
        [id]: `${action} failed: network error — the order was NOT ${action === "approve" ? "approved" : "rejected"}`,
      }));
    } finally {
      setBusy(null);
    }
  }

  if (!orders.length) {
    return (
      <p style={{ fontSize: 12, color: "#5c6773" }}>
        {loadErr
          ? "Order queue unavailable — retrying…"
          : "No orders yet. Run the agents — proposed trades land here for your approval."}
      </p>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {loadErr && (
        <p style={{ fontSize: 11, color: "var(--amber)", margin: 0 }}>
          Queue refresh failed — showing last known state, retrying…
        </p>
      )}
      {orders.map((o) => (
        <div key={o.id} className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, fontSize: 12 }}>
            <span className="num" style={{ color: "#d6deeb" }}>
              <b style={{ textTransform: "uppercase", color: o.side === "buy" ? "#8fd694" : "#f7768e" }}>
                {o.side}
              </b>{" "}
              {o.qty} {o.symbol}
              {o.est_notional ? ` · ~$${o.est_notional}` : ""}
            </span>
            <span className="badge" style={{ color: STATUS_COLOR[o.status] ?? "#9aa5b1" }}>
              {o.status.replace("_", " ")}
            </span>
          </div>
          <div style={{ fontSize: 10, color: "#5c6773", margin: "4px 0 6px" }}>
            {o.id} · {o.order_type} · {o.source ?? "human"}
            {o.est_price ? ` · est $${o.est_price}` : ""}
            {age(o.created_ts) ? ` · proposed ${age(o.created_ts)}` : ""}
            {o.broker_result?.status ? ` · ${o.broker_result.status}` : ""}
          </div>
          {o.thesis ? (
            <div style={{ fontSize: 11, color: "var(--text-dim)", margin: "0 0 6px", fontStyle: "italic" }}>
              {o.thesis}
            </div>
          ) : null}
          {errors[o.id] ? (
            <div role="alert" style={{ fontSize: 11, color: "var(--red)", margin: "0 0 6px" }}>
              {errors[o.id]}
            </div>
          ) : null}
          {o.status === "PENDING_APPROVAL" &&
            (confirming === o.id ? (
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, color: "var(--amber)" }}>
                  Confirm {o.side.toUpperCase()} {o.qty} {o.symbol}
                  {o.est_notional ? ` (~$${o.est_notional})` : ""}?
                </span>
                <button onClick={() => act(o.id, "approve")} disabled={busy === o.id} className="btn btn-ok">
                  Confirm
                </button>
                <button onClick={() => setConfirming(null)} disabled={busy === o.id} className="btn">
                  Cancel
                </button>
              </div>
            ) : (
              <div style={{ display: "flex", gap: 6 }}>
                <button onClick={() => setConfirming(o.id)} disabled={busy === o.id} className="btn btn-ok">
                  Approve
                </button>
                <button onClick={() => act(o.id, "reject")} disabled={busy === o.id} className="btn btn-danger">
                  Reject
                </button>
              </div>
            ))}
        </div>
      ))}
    </div>
  );
}
