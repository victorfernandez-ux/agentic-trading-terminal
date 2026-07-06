"use client";

/**
 * Alert rules: create, list, pause/resume, delete. Evaluation happens
 * server-side (4s fast tier, ~60s indicator tier); fired events arrive on
 * the quote socket and via polling here. Alerts notify — they never trade.
 */

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Alert = {
  id: string;
  status: "active" | "paused" | "fired";
  symbol: string;
  metric: string;
  op: string;
  value: number;
  trigger: string;
  auto_research?: boolean;
  fired_count: number;
  last_state: { side: string; value: number } | null;
};

const dim = "#5c6773";
const METRIC_LABEL: Record<string, string> = {
  price: "price",
  pct_change_day: "day %",
  rsi14: "RSI14",
  signal_score: "signal",
};
const OP_LABEL: Record<string, string> = {
  crosses_above: "crosses ↑",
  crosses_below: "crosses ↓",
  gt: ">",
  lt: "<",
};

export default function Alerts({ symbol }: { symbol: string }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [metric, setMetric] = useState("price");
  const [op, setOp] = useState("crosses_above");
  const [value, setValue] = useState<string>("");
  const [trigger, setTrigger] = useState("once");
  const [autoResearch, setAutoResearch] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await apiFetch("/api/alerts");
      const j = await r.json();
      setAlerts(j.alerts ?? []);
    } catch {
      /* backend offline — list stays stale */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 10_000);
    return () => clearInterval(t);
  }, [load]);

  async function create() {
    setErr(null);
    const v = parseFloat(value);
    if (!isFinite(v)) {
      setErr("enter a numeric level");
      return;
    }
    const r = await apiFetch("/api/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, metric, op, value: v, trigger, auto_research: autoResearch }),
    });
    if (!r.ok) setErr((await r.json()).detail ?? "create failed");
    else {
      setValue("");
      load();
    }
  }

  async function act(id: string, action: "pause" | "resume" | "delete") {
    if (action === "delete") await apiFetch(`/api/alerts/${id}`, { method: "DELETE" });
    else await apiFetch(`/api/alerts/${id}/${action}`, { method: "POST" });
    load();
  }

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
        <b style={{ color: "#7aa2f7" }}>{symbol}</b>
        <select value={metric} onChange={(e) => setMetric(e.target.value)} style={sel}>
          {Object.entries(METRIC_LABEL).map(([k, l]) => (
            <option key={k} value={k}>{l}</option>
          ))}
        </select>
        <select value={op} onChange={(e) => setOp(e.target.value)} style={sel}>
          {Object.entries(OP_LABEL).map(([k, l]) => (
            <option key={k} value={k}>{l}</option>
          ))}
        </select>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && create()}
          placeholder="level"
          style={{ ...sel, width: 90 }}
        />
        <select value={trigger} onChange={(e) => setTrigger(e.target.value)} style={sel}>
          <option value="once">once</option>
          <option value="every_time">every time</option>
        </select>
        <label
          style={{ display: "flex", alignItems: "center", gap: 4, color: autoResearch ? "#7aa2f7" : dim, cursor: "pointer" }}
          title="On fire, auto-run the research agents on the hit (rate-capped). Proposals only — orders still stop at the approval queue."
        >
          <input
            type="checkbox"
            checked={autoResearch}
            onChange={(e) => setAutoResearch(e.target.checked)}
          />
          🤖 research
        </label>
        <button onClick={create} style={btn}>+ Alert</button>
        {err && <span style={{ color: "#f7768e" }}>{err}</span>}
      </div>

      {alerts.length === 0 && (
        <p style={{ color: dim, margin: 0 }}>
          No alerts. They evaluate server-side and fire into the audit log + quote stream.
        </p>
      )}
      {alerts.map((a) => (
        <div
          key={a.id}
          style={{
            display: "flex",
            gap: 10,
            alignItems: "center",
            padding: "4px 0",
            color: a.status === "fired" ? "#e0af68" : a.status === "paused" ? dim : "#d6deeb",
          }}
        >
          <span style={{ color: a.status === "active" ? "#8fd694" : a.status === "fired" ? "#e0af68" : dim }}>
            {a.status === "active" ? "●" : a.status === "fired" ? "▲" : "‖"}
          </span>
          <span style={{ minWidth: 220 }}>
            <b>{a.symbol}</b> {METRIC_LABEL[a.metric] ?? a.metric} {OP_LABEL[a.op] ?? a.op}{" "}
            {a.value.toLocaleString()}
            <span style={{ color: dim }}> · {a.trigger === "once" ? "once" : "repeat"}</span>
            {a.auto_research && (
              <span title="fires into agent research (rate-capped; proposals only)"> 🤖</span>
            )}
          </span>
          <span style={{ color: dim }}>
            {a.last_state ? `now ${a.last_state.value?.toLocaleString?.() ?? a.last_state.value} (${a.last_state.side})` : "awaiting first tick"}
            {a.fired_count > 0 && ` · fired ${a.fired_count}x`}
          </span>
          <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            {a.status === "active" ? (
              <button onClick={() => act(a.id, "pause")} style={lnk}>pause</button>
            ) : (
              <button onClick={() => act(a.id, "resume")} style={lnk}>re-arm</button>
            )}
            <button onClick={() => act(a.id, "delete")} style={{ ...lnk, color: "#f7768e" }}>
              delete
            </button>
          </span>
        </div>
      ))}
    </div>
  );
}

const sel: React.CSSProperties = {
  background: "#0f1320", color: "#c0caf5", border: "1px solid #1c2330",
  borderRadius: 6, padding: "3px 6px", fontSize: 12, fontFamily: "inherit",
};
const btn: React.CSSProperties = {
  background: "#1f2a44", color: "#7aa2f7", border: "1px solid #1c2330",
  borderRadius: 6, padding: "3px 10px", cursor: "pointer", fontSize: 12,
};
const lnk: React.CSSProperties = {
  background: "transparent", border: "none", color: "#7aa2f7",
  cursor: "pointer", fontSize: 11, padding: 0,
};
