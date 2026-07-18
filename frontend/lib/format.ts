/** Shared display formatters (review: News and ApprovalQueue each carried
 *  their own time-ago implementation with drifting banding). */

/** Compact relative age: "42s" / "3m" / "5h" / "2d". Null when unknown. */
export function timeAgo(ts: number | null | undefined): string | null {
  if (!ts) return null;
  const s = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return h < 48 ? `${h}h` : `${Math.floor(h / 24)}d`;
}
