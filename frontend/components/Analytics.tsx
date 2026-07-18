"use client";

/**
 * Analytics panel — the five FinceptTerminal-inspired capabilities:
 * indicators+signal, risk metrics, backtesting, DCF valuation, and
 * investor-persona scoring. Each tab calls its /analytics endpoint for
 * the selected symbol and renders a compact, scannable summary.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { createChart, type IChartApi } from "lightweight-charts";
import { observeChartWidth } from "@/lib/chartWidth";

const TABS = ["Signal", "Risk", "Backtest", "DCF", "Personas", "Options", "Screener", "Corr", "Behavior"] as const;
type Tab = (typeof TABS)[number];

const dim = "#5c6773";
const green = "#8fd694";
const red = "#f7768e";
const blue = "#7aa2f7";

const cell: React.CSSProperties = { padding: "2px 8px 2px 0", whiteSpace: "nowrap" };

// View types for the rows each tab renders (H3): only the fields the JSX
// below actually reads. Full per-endpoint payload types land with the
// planned per-tab split (hardening roadmap H7).
type ScreenMatch = {
  symbol: string;
  price?: number | null;
  day_pct?: number | null;
  rsi14?: number | null;
  rvol?: number | null;
  pct_of_52w_high?: number | null;
  signal_score: number;
  matched?: string[];
};
type SignalVote = { factor: string; vote: number; detail: string };
type OptionRow = {
  strike: number;
  bid?: number | null;
  ask?: number | null;
  iv?: number | null;
  delta?: number | null;
  oi?: number | null;
  itm?: boolean;
};
type PersonaScore = { persona: string; score: number; verdict: string };
type BacktestTrade = {
  entry_t: number;
  entry_price: number;
  exit_t: number;
  exit_price: number;
  pnl_pct: number;
};
type WalkForward = {
  error?: string;
  holds?: boolean;
  one_regime?: boolean;
  positive_windows?: number;
  n_windows?: number;
  worst_window_pct?: number;
};
type BootstrapBand = { p5?: number; p50?: number; p95?: number };
type BenchmarkPanel = {
  error?: string;
  benchmark?: string;
  excess_return_pct?: number;
  information_ratio?: number;
  curve?: { t: number; equity: number }[];
};

function Num({ v, suffix = "", colorize = false }: { v: number | null | undefined; suffix?: string; colorize?: boolean }) {
  if (v === null || v === undefined) return <span style={{ color: dim }}>—</span>;
  const color = colorize ? (v >= 0 ? green : red) : undefined;
  return <span style={{ color }}>{v.toLocaleString(undefined, { maximumFractionDigits: 2 })}{suffix}</span>;
}

function KV({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <table style={{ fontSize: 12, borderCollapse: "collapse" }}>
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <td style={{ ...cell, color: dim }}>{k}</td>
            <td style={cell}>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Analytics({
  symbol,
  onSelect,
  watchlist = [],
}: {
  symbol: string;
  onSelect?: (symbol: string) => void;
  watchlist?: string[];
}) {
  const [tab, setTab] = useState<Tab>("Signal");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [strategy, setStrategy] = useState("sma_cross");
  const [expiration, setExpiration] = useState<number | null>(null);
  const [screen, setScreen] = useState("composite_bullish");
  const [universe, setUniverse] = useState("sp100");
  // DCF inputs (billions for fcf/shares/debt keeps typing sane)
  const [dcf, setDcf] = useState({ fcf: 100, shares: 15, netDebt: 50, growth: 6, wacc: 9, tg: 2.5 });

  const run = useCallback(async () => {
    setBusy(true);
    setData(null);
    try {
      let res: Response;
      if (tab === "Signal") {
        res = await apiFetch(`/api/analytics/indicators?symbol=${encodeURIComponent(symbol)}&limit=200`);
      } else if (tab === "Risk") {
        res = await apiFetch(`/api/analytics/risk?symbol=${encodeURIComponent(symbol)}&benchmark=SPY`);
      } else if (tab === "Backtest") {
        res = await apiFetch(`/api/analytics/backtest`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          // Credibility layer on: walk-forward + bootstrap bands, auto
          // benchmark, and a saved run card per run.
          body: JSON.stringify({ symbol, strategy, limit: 365, validate_run: true, save_card: true }),
        });
      } else if (tab === "DCF") {
        res = await apiFetch(`/api/analytics/dcf`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol,
            fcf: dcf.fcf * 1e9,
            shares_outstanding: dcf.shares * 1e9,
            net_debt: dcf.netDebt * 1e9,
            growth_rate: dcf.growth / 100,
            wacc: dcf.wacc / 100,
            terminal_growth: dcf.tg / 100,
          }),
        });
      } else if (tab === "Personas") {
        res = await apiFetch(`/api/analytics/personas`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol, fundamentals: {} }),
        });
      } else if (tab === "Options") {
        const exp = expiration ? `&expiration=${expiration}` : "";
        res = await apiFetch(
          `/api/analytics/options/chain?symbol=${encodeURIComponent(symbol)}&strikes_around=10${exp}`
        );
      } else if (tab === "Corr") {
        res = await apiFetch(
          `/api/analytics/correlations?symbols=${encodeURIComponent(watchlist.join(","))}&window=60`
        );
      } else if (tab === "Behavior") {
        res = await apiFetch(`/api/analytics/behavior`);
      } else {
        res = await apiFetch(
          `/api/analytics/screener?screen=${screen}&universe=${universe}&top=15`
        );
      }
      setData(await res.json());
    } catch {
      setData({ error: "request failed — backend offline?" });
    } finally {
      setBusy(false);
    }
  }, [tab, symbol, strategy, dcf, screen, universe, expiration, watchlist]);

  // Auto-run the cheap GET tabs when symbol/tab changes; POST tabs run on demand.
  useEffect(() => {
    setData(null);
    if (tab !== "Options") setExpiration(null);
    if (tab === "Signal" || tab === "Risk" || tab === "Options" || tab === "Corr" || tab === "Behavior") void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, symbol, expiration]);

  // Single untyped seam: nine endpoint payloads share this one state slot,
  // so per-field types live on the render helpers below instead. Goes away
  // with the per-tab split (hardening roadmap H7).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const d = (data ?? {}) as Record<string, any>;

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`tab${tab === t ? " active" : ""}`}>
            {t}
          </button>
        ))}
        <span style={{ marginLeft: "auto", color: dim, alignSelf: "center" }}>{symbol}</span>
      </div>

      {tab === "Backtest" && (
        <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="select">
            <option value="sma_cross">SMA cross (10/30)</option>
            <option value="rsi_reversion">RSI reversion</option>
            <option value="buy_hold">Buy & hold</option>
          </select>
          <button onClick={run} disabled={busy} className="btn">{busy ? "running…" : "Run backtest"}</button>
        </div>
      )}

      {tab === "DCF" && (
        <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }}>
          {(
            [
              ["FCF $B", "fcf"],
              ["Shares B", "shares"],
              ["NetDebt $B", "netDebt"],
              ["Growth %", "growth"],
              ["WACC %", "wacc"],
              ["Term %", "tg"],
            ] as [string, keyof typeof dcf][]
          ).map(([label, key]) => (
            <label key={key} style={{ color: dim }}>
              {label}{" "}
              <input
                type="number"
                value={dcf[key]}
                step="0.5"
                onChange={(e) => setDcf({ ...dcf, [key]: Number(e.target.value) })}
                className="input num"
                style={{ width: 64 }}
              />
            </label>
          ))}
          <button onClick={run} disabled={busy} className="btn">{busy ? "valuing…" : "Value it"}</button>
        </div>
      )}

      {tab === "Screener" && (
        <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
          <select value={screen} onChange={(e) => setScreen(e.target.value)} className="select">
            <option value="composite_bullish">Composite bullish</option>
            <option value="composite_bearish">Composite bearish</option>
            <option value="rsi_oversold">RSI oversold</option>
            <option value="rsi_overbought">RSI overbought</option>
            <option value="uptrend">Uptrend</option>
            <option value="big_gainers">Big gainers</option>
            <option value="big_losers">Big losers</option>
            <option value="near_52w_high">Near 52w high</option>
            <option value="unusual_volume">Unusual volume</option>
          </select>
          <select value={universe} onChange={(e) => setUniverse(e.target.value)} className="select">
            <option value="sp100">S&P 100</option>
            <option value="indices">Global indices</option>
            <option value="fx">FX majors</option>
            <option value="futures">Futures</option>
            <option value="crypto">Crypto</option>
          </select>
          <button onClick={run} disabled={busy} className="btn">
            {busy ? "scanning…" : "Scan"}
          </button>
          {d.scanned !== undefined && (
            <span style={{ color: dim }}>
              {d.matches?.length ?? 0} hits / {d.scanned} scanned
            </span>
          )}
        </div>
      )}

      {tab === "Screener" && Array.isArray(d.matches) && d.matches.length > 0 && (
        <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%" }}>
          <thead>
            <tr style={{ color: dim, textAlign: "right" }}>
              <th style={{ ...cell, textAlign: "left" }}>Symbol</th>
              <th style={cell}>Price</th><th style={cell}>Day %</th>
              <th style={cell}>RSI14</th><th style={cell}>RVOL</th>
              <th style={cell}>% of 52w hi</th><th style={cell}>Signal</th>
              <th style={{ ...cell, textAlign: "left" }}>Why</th>
            </tr>
          </thead>
          <tbody style={{ textAlign: "right" }}>
            {d.matches.map((m: ScreenMatch) => (
              <tr
                key={m.symbol}
                onClick={() => onSelect?.(m.symbol)}
                className="tr-hover num"
                style={{ cursor: onSelect ? "pointer" : undefined }}
                title="click to load in the terminal"
              >
                <td style={{ ...cell, textAlign: "left", color: blue }}>{m.symbol}</td>
                <td style={cell}><Num v={m.price} /></td>
                <td style={cell}><Num v={m.day_pct} suffix="%" colorize /></td>
                <td style={cell}><Num v={m.rsi14} /></td>
                <td style={cell}><Num v={m.rvol} /></td>
                <td style={cell}><Num v={m.pct_of_52w_high} suffix="%" /></td>
                <td style={cell}>{m.signal_score >= 0 ? `+${m.signal_score}` : m.signal_score}</td>
                <td style={{ ...cell, textAlign: "left", color: dim }}>{(m.matched ?? []).join("; ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {tab === "Screener" && Array.isArray(d.matches) && d.matches.length === 0 && d.scanned !== undefined && !busy && (
        <p style={{ color: dim }}>no matches — try another screen or universe</p>
      )}

      {tab === "Corr" && Array.isArray(d.symbols) && d.symbols.length > 1 && (
        <CorrHeatmap
          symbols={d.symbols}
          matrix={d.matrix}
          avg={d.avg_abs_correlation}
          window={d.window}
          skipped={d.skipped}
        />
      )}

      {tab === "Behavior" && d.proposals_decided !== undefined && (
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <KV
            rows={[
              ["Decided (appr/rej)", <span key="1">{d.proposals_decided} ({d.approved}/{d.rejected})</span>],
              ["Approval rate", <Num key="2" v={d.approval_rate_pct} suffix="%" />],
              ["Buy vs sell appr.", <span key="3">
                <Num v={d.by_side?.buy?.approval_rate_pct} suffix="%" /> / <Num v={d.by_side?.sell?.approval_rate_pct} suffix="%" />
              </span>],
              ["Max fills / day", <span key="4">{d.activity?.max_fills_per_day ?? "—"}</span>],
            ]}
          />
          <KV
            rows={[
              ["Realized P&L", <Num key="1" v={d.outcomes?.realized_pnl} suffix=" $" colorize />],
              ["Win rate", <Num key="2" v={d.outcomes?.win_rate_pct} suffix="%" />],
              ["Hold: winners / losers", <span key="3">
                <Num v={d.outcomes?.avg_hold_days_winners} suffix="d" /> / <Num v={d.outcomes?.avg_hold_days_losers} suffix="d" />
                {d.outcomes?.disposition_effect ? <b style={{ color: red }}> ⚠ disposition</b> : null}
              </span>],
              ["Rejections would be", d.rejections?.counterfactual_pnl != null ? (
                <span key="4">
                  <Num v={d.rejections.counterfactual_pnl} suffix=" $" colorize />{" "}
                  <span style={{ color: dim }}>
                    ({d.rejections.counterfactual_pnl > 0 ? "missed gains" : "dodged losses"}, {d.rejections.evaluated} orders)
                  </span>
                </span>
              ) : (<span key="4" style={{ color: dim }}>—</span>)],
            ]}
          />
        </div>
      )}

      {tab === "Personas" && !data && (
        <button onClick={run} disabled={busy} className="btn" style={{ marginBottom: 8 }}>
          {busy ? "consulting…" : "Consult the legends"}
        </button>
      )}

      {busy && !data && <p style={{ color: dim }}>computing…</p>}
      {d.error && (
        <p style={{ color: red }}>
          {typeof d.error === "string" ? d.error : d.error?.message ?? "request failed"}
        </p>
      )}

      {tab === "Signal" && d.signal && (
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <KV
            rows={[
              ["Composite", <b key="c" style={{ color: d.signal.label === "bullish" ? green : d.signal.label === "bearish" ? red : dim }}>
                {d.signal.label.toUpperCase()} ({d.signal.score >= 0 ? "+" : ""}{d.signal.score})</b>],
              ["Close", <Num key="v" v={d.latest?.close} />],
              ["SMA20 / 50", <span key="s"><Num v={d.latest?.sma20} /> / <Num v={d.latest?.sma50} /></span>],
              ["RSI14", <Num key="r" v={d.latest?.rsi14} />],
              ["MACD hist", <Num key="m" v={d.latest?.macd_hist} colorize />],
              ["ATR14", <Num key="a" v={d.latest?.atr14} />],
            ]}
          />
          <ul style={{ margin: 0, paddingLeft: 16, color: dim, maxWidth: 420 }}>
            {(d.signal.votes ?? []).map((v: SignalVote) => (
              <li key={v.factor} style={{ color: v.vote > 0 ? green : v.vote < 0 ? red : dim }}>{v.detail}</li>
            ))}
          </ul>
        </div>
      )}

      {tab === "Risk" && d.sharpe !== undefined && (
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <KV
            rows={[
              ["Total return", <Num key="1" v={d.total_return_pct} suffix="%" colorize />],
              ["CAGR", <Num key="2" v={d.cagr_pct} suffix="%" colorize />],
              ["Volatility (ann)", <Num key="3" v={d.volatility_ann_pct} suffix="%" />],
              ["Sharpe / Sortino", <span key="4"><Num v={d.sharpe} /> / <Num v={d.sortino} /></span>],
            ]}
          />
          <KV
            rows={[
              ["Max drawdown", <Num key="1" v={d.max_drawdown_pct} suffix="%" colorize />],
              ["VaR 95 / CVaR 95", <span key="2"><Num v={d.var_95_pct} suffix="%" /> / <Num v={d.cvar_95_pct} suffix="%" /></span>],
              ["Win rate", <Num key="3" v={d.win_rate_pct} suffix="%" />],
              ["Beta / α vs SPY", d.benchmark_metrics ? (
                <span key="4"><Num v={d.benchmark_metrics.beta} /> / <Num v={d.benchmark_metrics.alpha_ann_pct} suffix="%" colorize /></span>
              ) : (<span key="4" style={{ color: dim }}>—</span>)],
            ]}
          />
        </div>
      )}

      {tab === "Backtest" && d.final_equity !== undefined && (
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <KV
            rows={[
              ["Strategy return", <Num key="1" v={d.total_return_pct} suffix="%" colorize />],
              ["Buy & hold", <Num key="2" v={d.buy_hold_return_pct} suffix="%" colorize />],
              ["Final equity", <Num key="3" v={d.final_equity} suffix=" $" />],
              ["Trades / win rate", <span key="4">{d.n_trades} / <Num v={d.win_rate_pct} suffix="%" /></span>],
            ]}
          />
          <KV
            rows={[
              ["Sharpe", <Num key="1" v={d.metrics?.sharpe} />],
              ["Max drawdown", <Num key="2" v={d.metrics?.max_drawdown_pct} suffix="%" colorize />],
              ["Bars tested", <span key="3">{d.bars_count}</span>],
              ["Fees", <span key="4">{d.fee_bps} bps/side</span>],
            ]}
          />
          <Validation validation={d.validation} benchmark={d.benchmark} runCard={d.run_card} />
          <TradeList trades={d.trades} />
          {Array.isArray(d.equity_curve) && d.equity_curve.length > 1 && (
            <div style={{ flexBasis: "100%" }}>
              <EquityChart points={d.equity_curve} benchmark={d.benchmark?.curve} />
            </div>
          )}
        </div>
      )}

      {tab === "DCF" && d.fair_value_per_share !== undefined && (
        <KV
          rows={[
            ["Fair value / share", <b key="1" style={{ color: blue }}><Num v={d.fair_value_per_share} suffix=" $" /></b>],
            ["Market price", <Num key="2" v={d.current_price} suffix=" $" />],
            ["Upside", <Num key="3" v={d.upside_pct} suffix="%" colorize />],
            ["Verdict", <b key="4" style={{ color: d.verdict === "undervalued" ? green : d.verdict === "overvalued" ? red : dim }}>{d.verdict ?? "—"}</b>],
            ["PV explicit / equity", <span key="5"><Num v={d.pv_explicit && d.pv_explicit / 1e9} suffix="B" /> / <Num v={d.equity_value && d.equity_value / 1e9} suffix="B" /></span>],
          ]}
        />
      )}

      {tab === "Options" && d.calls && (
        <div style={{ fontSize: 12 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 8 }}>
            <span style={{ color: dim }}>
              spot <b style={{ color: "#d6deeb" }}><Num v={d.spot} /></b>
            </span>
            <select
              value={d.expiration ?? ""}
              onChange={(e) => setExpiration(Number(e.target.value))}
              className="select"
            >
              {(d.expirations ?? []).map((x: number) => (
                <option key={x} value={x}>
                  exp {new Date(x * 1000).toISOString().slice(0, 10)}
                </option>
              ))}
            </select>
            <span style={{ color: dim }}>T = {d.t_years} y · Greeks from chain IV</span>
          </div>
          <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%" }}>
            <thead>
              <tr style={{ color: dim, textAlign: "right" }}>
                <th style={cell}>C bid/ask</th><th style={cell}>C IV</th>
                <th style={cell}>C Δ</th><th style={cell}>OI</th>
                <th style={{ ...cell, textAlign: "center", color: blue }}>Strike</th>
                <th style={cell}>OI</th><th style={cell}>P Δ</th>
                <th style={cell}>P IV</th><th style={cell}>P bid/ask</th>
              </tr>
            </thead>
            <tbody style={{ textAlign: "right" }}>
              {(d.calls ?? []).map((c: OptionRow, i: number) => {
                const p: Partial<OptionRow> =
                  (d.puts ?? []).find((x: OptionRow) => x.strike === c.strike) ?? {};
                const atm = Math.abs(c.strike - d.spot) ===
                  Math.min(...(d.calls ?? []).map((x: OptionRow) => Math.abs(x.strike - d.spot)));
                return (
                  <tr key={i} className="tr-hover num" style={{ background: atm ? "#16203a" : undefined }}>
                    <td style={{ ...cell, color: c.itm ? green : undefined }}>
                      {c.bid ?? "—"}/{c.ask ?? "—"}
                    </td>
                    <td style={cell}>{c.iv ? (c.iv * 100).toFixed(1) + "%" : "—"}</td>
                    <td style={cell}>{c.delta ?? "—"}</td>
                    <td style={cell}>{c.oi ?? "—"}</td>
                    <td style={{ ...cell, textAlign: "center", color: blue }}>{c.strike}</td>
                    <td style={cell}>{p.oi ?? "—"}</td>
                    <td style={cell}>{p.delta ?? "—"}</td>
                    <td style={cell}>{p.iv ? (p.iv * 100).toFixed(1) + "%" : "—"}</td>
                    <td style={{ ...cell, color: p.itm ? green : undefined }}>
                      {p.bid ?? "—"}/{p.ask ?? "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {tab === "Personas" && d.consensus && (
        <div>
          <p style={{ margin: "0 0 8px" }}>
            Consensus:{" "}
            <b style={{ color: d.consensus.verdict === "BULLISH" ? green : d.consensus.verdict === "BEARISH" ? red : dim }}>
              {d.consensus.verdict}
            </b>{" "}
            {d.consensus.score !== null && <span style={{ color: dim }}>(score {d.consensus.score}, {d.consensus.personas_scored}/5 personas opined)</span>}
          </p>
          {(d.personas ?? []).map((p: PersonaScore) => (
            <div key={p.persona} style={{ display: "grid", gridTemplateColumns: "130px 1fr 60px 110px", gap: 8, alignItems: "center", padding: "3px 0" }}>
              <span>{p.persona}</span>
              <div style={{ background: "#1c2330", borderRadius: 4, height: 8 }}>
                <div
                  style={{
                    width: `${p.score}%`,
                    height: 8,
                    borderRadius: 4,
                    background: p.score >= 70 ? green : p.score >= 45 ? "#e0af68" : red,
                    opacity: p.verdict === "INSUFFICIENT_DATA" ? 0.25 : 1,
                  }}
                />
              </div>
              <span style={{ textAlign: "right" }}>{p.verdict === "INSUFFICIENT_DATA" ? "—" : p.score}</span>
              <span style={{ color: dim, fontSize: 11 }}>{p.verdict.replace("_", " ").toLowerCase()}</span>
            </div>
          ))}
          <p style={{ color: dim, marginTop: 8, fontSize: 11 }}>
            Price-action only — pass fundamentals via the API or agent tools for full coverage.
          </p>
        </div>
      )}
    </div>
  );
}

// Walk-forward verdict + bootstrap bands + benchmark excess (roadmap B).
function Validation({
  validation,
  benchmark,
  runCard,
}: {
  validation?: {
    walk_forward?: WalkForward;
    monte_carlo?: { error?: string; return_pct?: BootstrapBand };
  };
  benchmark?: BenchmarkPanel;
  runCard?: { id: string };
}) {
  const wf = validation?.walk_forward;
  const mc = validation?.monte_carlo;
  if (!wf && !mc && !benchmark) return null;
  const verdict = wf?.error
    ? "—"
    : wf?.holds
      ? "HOLDS"
      : wf?.one_regime
        ? "ONE-REGIME"
        : "weak";
  const verdictColor = wf?.holds ? green : wf?.one_regime ? red : dim;
  const r = mc?.return_pct;
  return (
    <KV
      rows={[
        ["Walk-forward", <span key="1">
          <b style={{ color: verdictColor }}>{verdict}</b>
          {wf && !wf.error ? <span style={{ color: dim }}> · {wf.positive_windows}/{wf.n_windows} windows +, worst <Num v={wf.worst_window_pct} suffix="%" colorize /></span> : null}
        </span>],
        ["Bootstrap return", r ? (
          <span key="2"><Num v={r.p5} suffix="%" colorize /> / <Num v={r.p50} suffix="%" colorize /> / <Num v={r.p95} suffix="%" colorize /> <span style={{ color: dim }}>(P5/P50/P95)</span></span>
        ) : (<span key="2" style={{ color: dim }}>{mc?.error ?? "—"}</span>)],
        ["vs benchmark", benchmark && !benchmark.error ? (
          <span key="3">{benchmark.benchmark}: excess <Num v={benchmark.excess_return_pct} suffix="%" colorize /> · IR <Num v={benchmark.information_ratio} /></span>
        ) : (<span key="3" style={{ color: dim }}>{benchmark?.error ?? "—"}</span>)],
        ["Run card", <span key="4" style={{ color: dim }}>{runCard?.id ?? "—"}</span>],
      ]}
    />
  );
}

function EquityChart({
  points,
  benchmark,
}: {
  points: { t: number; equity: number }[];
  benchmark?: { t: number; equity: number }[];
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || points.length === 0) return;
    const chart: IChartApi = createChart(el, {
      height: 170,
      layout: { background: { color: "transparent" }, textColor: "#5c6773", fontSize: 10 },
      grid: { vertLines: { color: "#141a26" }, horzLines: { color: "#141a26" } },
      rightPriceScale: { borderColor: "#1c2330" },
      timeScale: { borderColor: "#1c2330" },
    });
    const series = chart.addAreaSeries({
      lineColor: "#7aa2f7",
      topColor: "#7aa2f733",
      bottomColor: "#7aa2f705",
      lineWidth: 2,
    });
    series.setData(
      points.map((p) => ({ time: Math.floor(p.t / 1000) as never, value: p.equity }))
    );
    // Benchmark overlay (buy-and-hold, rebased server-side to the same
    // starting equity) — the "did it beat doing nothing" line.
    if (benchmark && benchmark.length > 1) {
      const bench = chart.addLineSeries({
        color: "#e0af68",
        lineWidth: 1,
        lineStyle: 2, // dashed
        priceLineVisible: false,
        lastValueVisible: false,
      });
      bench.setData(
        benchmark.map((p) => ({ time: Math.floor(p.t / 1000) as never, value: p.equity }))
      );
    }
    chart.timeScale().fitContent();
    const unobserve = observeChartWidth(el, chart);
    return () => {
      unobserve();
      chart.remove();
    };
  }, [points, benchmark]);

  return <div ref={ref} style={{ width: "100%", marginTop: 10 }} />;
}

// Watchlist return-correlation heatmap (roadmap C3). Green = negative
// correlation (diversifying), red = positive (concentrated).
function CorrHeatmap({
  symbols,
  matrix,
  avg,
  window,
  skipped,
}: {
  symbols: string[];
  matrix: (number | null)[][];
  avg?: number | null;
  window?: number;
  skipped?: string[];
}) {
  const bg = (v: number | null) => {
    if (v === null) return "transparent";
    const a = Math.min(Math.abs(v), 1) * 0.55;
    return v >= 0 ? `rgba(247, 118, 142, ${a})` : `rgba(143, 214, 148, ${a})`;
  };
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="num" style={{ fontSize: 10, borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={cell} />
            {symbols.map((s) => (
              <th key={s} style={{ ...cell, color: dim }}>{s}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {symbols.map((a, i) => (
            <tr key={a}>
              <td style={{ ...cell, color: dim }}>{a}</td>
              {symbols.map((b, j) => (
                <td key={b} style={{ ...cell, textAlign: "center", background: bg(matrix[i]?.[j] ?? null) }}>
                  {matrix[i]?.[j] === null || matrix[i]?.[j] === undefined ? "—" : matrix[i][j]!.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ color: dim, marginTop: 6 }}>
        {window}d returns · avg |ρ| {avg ?? "—"}
        {skipped?.length ? ` · skipped (thin history): ${skipped.join(", ")}` : ""}
      </p>
    </div>
  );
}

function TradeList({ trades }: { trades: BacktestTrade[] }) {
  if (!trades?.length) return null;
  const fmt = (t: number) => new Date(t).toISOString().slice(0, 10);
  return (
    <table style={{ fontSize: 11, borderCollapse: "collapse", marginTop: 8 }}>
      <thead>
        <tr style={{ color: dim, textAlign: "left" }}>
          <th style={cell}>Entry</th><th style={cell}>@</th>
          <th style={cell}>Exit</th><th style={cell}>@</th>
          <th style={cell}>P&L</th>
        </tr>
      </thead>
      <tbody>
        {trades.slice(-8).map((t, i) => (
          <tr key={i}>
            <td style={cell}>{fmt(t.entry_t)}</td>
            <td style={cell}><Num v={t.entry_price} /></td>
            <td style={cell}>{fmt(t.exit_t)}</td>
            <td style={cell}><Num v={t.exit_price} /></td>
            <td style={cell}><Num v={t.pnl_pct} suffix="%" colorize /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
