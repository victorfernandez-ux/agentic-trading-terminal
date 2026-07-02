"use client";

/**
 * Agent console — streams the run live over SSE (per-node progress from the
 * LangGraph engine), falling back to the one-shot POST if the stream fails.
 */

import { useRef, useState } from "react";

type Debate = {
  bull?: string;
  bear?: string;
  decision?: string;
  confidence?: number | null;
  judge_rationale?: string;
} | null;

type Result = {
  symbol: string;
  thesis: string;
  direction?: string;
  debate?: Debate;
  proposed_action: string | null;
  order: Record<string, unknown> | null;
  order_id: string | null;
  rationale: string[];
  error?: string;
};

type Step = { node: string; status: "start" | "end"; text: string };

const NODE_ICON: Record<string, string> = {
  evidence: "🧰",
  research: "🔎",
  debate: "⚖️",
  risk: "🛡",
  portfolio: "📋",
};

export default function AgentConsole({
  symbol,
  onProposed,
}: {
  symbol: string;
  onProposed: () => void;
}) {
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  function finish(j: Result) {
    setResult(j);
    setRunning(false);
    if (j.order_id) onProposed(); // refresh the approval queue
  }

  async function runFallback() {
    try {
      const r = await fetch("/api/agents/propose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol }),
      });
      finish(await r.json());
    } catch {
      setErr("agent run failed — is the backend up?");
      setRunning(false);
    }
  }

  function run() {
    setRunning(true);
    setErr(null);
    setResult(null);
    setSteps([]);
    let gotAny = false;

    let es: EventSource;
    try {
      es = new EventSource(`/api/agents/propose/stream?symbol=${encodeURIComponent(symbol)}`);
    } catch {
      void runFallback();
      return;
    }
    esRef.current = es;

    es.onmessage = (m) => {
      gotAny = true;
      let ev: Record<string, unknown>;
      try {
        ev = JSON.parse(m.data);
      } catch {
        return;
      }
      if (ev.event === "step") {
        const node = String(ev.node);
        const status = ev.status as "start" | "end";
        const text = String(status === "end" ? ev.summary ?? "" : ev.label ?? "");
        setSteps((prev) => {
          const others = prev.filter((s) => s.node !== node);
          return [...others, { node, status, text }];
        });
      } else if (ev.event === "result") {
        es.close();
        finish(ev as unknown as Result);
      } else if (ev.event === "error") {
        es.close();
        setErr(String(ev.error ?? "agent stream error"));
        setRunning(false);
      } else if (ev.event === "done") {
        es.close();
      }
    };
    es.onerror = () => {
      es.close();
      if (!gotAny) void runFallback(); // stream unsupported → one-shot POST
      else if (!result) setRunning(false);
    };
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <button onClick={run} disabled={running} style={btn(running)}>
        {running ? "Running agents…" : `▶ Run agents on ${symbol}`}
      </button>

      {steps.length > 0 && (
        <div style={{ fontSize: 12, lineHeight: 1.7 }}>
          {steps.map((s) => (
            <div key={s.node} style={{ color: s.status === "end" ? "#9aa5b1" : "#7aa2f7" }}>
              {s.status === "end" ? "✓" : <Spinner />} {NODE_ICON[s.node] ?? "•"}{" "}
              <b style={{ color: "#d6deeb" }}>{s.node}</b> — {s.text}
            </div>
          ))}
        </div>
      )}

      {err && <div style={{ color: "#f7768e", fontSize: 12 }}>{err}</div>}

      {result && (
        <div style={{ fontSize: 12, lineHeight: 1.5, color: "#d6deeb" }}>
          <div style={{ color: "#7aa2f7", marginBottom: 4 }}>
            {result.symbol} · direction: {result.direction ?? "—"}
          </div>
          <p style={{ margin: "0 0 8px" }}>{result.thesis}</p>

          {result.debate && (result.debate.bull || result.debate.bear) && (
            <div style={{ display: "flex", gap: 6, margin: "0 0 8px" }}>
              {result.debate.bull && (
                <div style={debateBox("#8fd694")}>
                  <b style={{ color: "#8fd694" }}>▲ Bull</b>
                  <div>{result.debate.bull}</div>
                </div>
              )}
              {result.debate.bear && (
                <div style={debateBox("#f7768e")}>
                  <b style={{ color: "#f7768e" }}>▼ Bear</b>
                  <div>{result.debate.bear}</div>
                </div>
              )}
            </div>
          )}

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

function Spinner() {
  return (
    <span
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        border: "2px solid #1c2330",
        borderTopColor: "#7aa2f7",
        borderRadius: "50%",
        animation: "attspin 0.8s linear infinite",
      }}
    >
      <style>{`@keyframes attspin { to { transform: rotate(360deg); } }`}</style>
    </span>
  );
}

const btn = (busy: boolean): React.CSSProperties => ({
  background: busy ? "#141a2a" : "#1f2a44",
  color: busy ? "#5c6773" : "#7aa2f7",
  border: "1px solid #1c2330",
  borderRadius: 6,
  padding: "8px 12px",
  cursor: busy ? "wait" : "pointer",
  fontSize: 13,
});

const tag = (color: string): React.CSSProperties => ({
  display: "inline-block",
  border: `1px solid ${color}44`,
  color,
  borderRadius: 6,
  padding: "4px 8px",
});

const debateBox = (color: string): React.CSSProperties => ({
  flex: 1,
  border: `1px solid ${color}33`,
  borderRadius: 6,
  padding: "6px 8px",
  color: "#9aa5b1",
  fontSize: 11,
  lineHeight: 1.4,
});
