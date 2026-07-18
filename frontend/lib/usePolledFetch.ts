"use client";

/** Shared polling data hook (H3c).
 *
 * Replaces the hand-rolled useEffect + useState + setInterval + apiFetch
 * boilerplate that was copy-pasted across the panels. Semantics chosen for
 * a trading terminal:
 *  - non-OK / network failures set `error` but KEEP the last-known data —
 *    blanking a panel on a blip misreads as "nothing exists";
 *  - a stale in-flight response never overwrites a newer request (seq guard);
 *  - `reload()` lets mutations refresh immediately without waiting a tick.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

export type Polled<T> = {
  data: T | null;
  /** true after a failed load; clears on the next success */
  error: boolean;
  reload: () => void;
};

export function usePolledFetch<T = unknown>(
  url: string | null,
  intervalMs = 0,
  options?: {
    /** bump to force an immediate reload (e.g. after an approval) */
    refreshKey?: unknown;
    /** map the raw JSON before it lands in `data` */
    parse?: (json: unknown) => T;
    /** clear data when the url changes (per-symbol panels) */
    resetOnUrlChange?: boolean;
  },
): Polled<T> {
  const { refreshKey, parse, resetOnUrlChange } = options ?? {};
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState(false);
  // parse is typically an inline lambda — keep it out of the effect deps.
  const parseRef = useRef(parse);
  parseRef.current = parse;
  const seq = useRef(0);
  const lastUrl = useRef(url);

  const load = useCallback(async () => {
    if (!url) return;
    const mySeq = ++seq.current;
    try {
      const r = await apiFetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const json: unknown = await r.json();
      if (mySeq !== seq.current) return; // superseded by a newer request
      setData(parseRef.current ? parseRef.current(json) : (json as T));
      setError(false);
    } catch {
      if (mySeq === seq.current) setError(true);
    }
  }, [url]);

  useEffect(() => {
    // Clear only on an ACTUAL url change (per-symbol/per-portfolio panels
    // must not show the previous target's data) — not on refreshKey bumps,
    // which would flash the empty state on every mutation.
    if (resetOnUrlChange && lastUrl.current !== url) {
      setData(null);
      setError(false);
    }
    lastUrl.current = url;
    load();
    if (intervalMs > 0) {
      const t = setInterval(load, intervalMs);
      return () => clearInterval(t);
    }
  }, [load, url, intervalMs, refreshKey, resetOnUrlChange]);

  return { data, error, reload: load };
}
