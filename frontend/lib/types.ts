/** Shared backend response shapes (H3d).
 *
 * One source of truth for the FastAPI payloads the components render.
 * Before this file every component redeclared its own copy, so a backend
 * field rename could silently drift past the type checker. Add new shared
 * shapes here; keep component-private view types in the component.
 */

export type Quote = {
  symbol: string;
  price: number | null;
  pct_change: number | null;
  provider?: string;
  error?: string;
};

export type Order = {
  id: string;
  symbol: string;
  side: string;
  qty: number;
  order_type: string;
  status: string;
  est_notional?: number;
  est_price?: number;
  created_ts?: number;
  thesis?: string | null;
  run_id?: string;
  source?: string;
  broker_result?: { status?: string; broker?: string };
};

export type Position = {
  symbol: string;
  qty: number;
  avg_cost: number;
  last: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
};

export type Portfolio = { id: string; name: string };

export type NewsItem = {
  title: string;
  link: string;
  source: string;
  published_ts: number | null;
};

export type AlertRule = {
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

export type FearGreedReading = {
  market: string;
  value?: number;
  label?: string;
  source?: string;
  error?: string;
};

export type Health = {
  status: string;
  trading_mode: string;
  require_human_approval: boolean;
};
