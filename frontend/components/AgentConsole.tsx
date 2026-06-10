"use client";

import { useState } from "react";

type Result = {
  symbol: string;
  thesis: string;
  direction?: string;
  proposed_action: string | null;
  order: Record<string, unknown> | null;
  order_id: string | null;
  rationale: string[];
};

export default function AgentConsole({
  symbol,
  onProposed,
}: {
  symbol: string;
  onProposed: () => void;
}) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setErr(null);
    setResult(null);
    try {
      const r = await fetch("/api/agents/propose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol }),
      });
      const j = await r.json();
      setResult(j);
      if (j.order_id) onProposed(); // refresh the approval queue
    } catch {
      setErr("agent run failed — is the backend up?");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <button onClick={run} disabled={running} style={btn(running)}>
        {running ? "Running agents…" : `▶ Run agents on ${symbol}`}
      </button>

      {err && <div style={{ color: "#f7768e", fontSize: 12 }}>{err}</div>}

      {result && (
        <div style={{ fontSize: 12, lineHeight: 1.5, color: "#d6deeb" }}>
          <div style={{ color: "#7aa2f7", marginBottom: 4 }}>
            {result.symbol} · direction: {result.direction ?? "—"}
          </div>
          <p style={{ margin: "0 0 8px" }}>{result.thesis}</p>

          {result.proposed_action ? (
            <div style={tag("#8fd694")}>📋 {result.proposed_action}</div>
          ) : (
            <div style={tag("#e0af68")}>No trade proposed (no edge / risk veto).</div>
          )}

          {result.order_id && (
            <div style={{ color: "#8fd694", marginTop: 6 }}>
              → Order {result.order_id} sent to Approval Queue.
            </div>
          )}

          {result.rationale?.length > 0 && (
            <ul style={{ margin: "8px 0 0", paddingLeft: 16, color: "#9aa5b1" }}>
              {result.rationale.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

const btn = (disabled: boolean): React.CSSProperties => ({
  padding: "8px 12px",
  borderRadius: 6,
  border: "1px solid #2a3550",
  background: disabled ? "#161b28" : "#1a2740",
  color: "#9ece6a",
  cursor: disabled ? "wait" : "pointer",
  fontFamily: "inherit",
  fontSize: 13,
});

const tag = (color: string): React.CSSProperties => ({
  border: `1px solid ${color}`,
  borderRadius: 6,
  padding: "6px 8px",
  color,
  fontSize: 12,
});
