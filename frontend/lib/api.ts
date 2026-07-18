"use client";

/** Single place for talking to the backend when API_TOKEN auth is enabled.
 *
 *  - apiFetch: fetch + "Authorization: Bearer <token>" from localStorage.
 *    On a 401 it fires an "att:unauthorized" window event so the page can
 *    show the token gate without every component handling auth.
 *  - tokenized: appends ?token= for clients that can't set headers
 *    (EventSource/SSE, WebSocket).
 *  With no token stored, requests go out unmodified — identical to the
 *  pre-auth behavior for unlocked local dev.
 */

const TOKEN_KEY = "att.token.v1";
export const UNAUTHORIZED_EVENT = "att:unauthorized";

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable — auth just won't persist */
  }
}

export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(input, { ...init, headers });
  if (res.status === 401) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  return res;
}

/** Portfolio filter query string. "default" keeps the unfiltered legacy
 *  view (orders may predate portfolio stamping); anything else filters
 *  server-side. Shared so the queue and positions can't drift. */
export function portfolioQuery(portfolio: string): string {
  return portfolio !== "default" ? `?portfolio_id=${encodeURIComponent(portfolio)}` : "";
}

/** Append ?token= (or &token=) to a URL for header-less clients (SSE/WS). */
export function tokenized(url: string): string {
  const token = getToken();
  if (!token) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
}

/** Preferred over tokenized(): mint a short-lived single-use ticket and
 *  append ?ticket= — the long-lived token stays out of URLs and server
 *  logs. Falls back to ?token= if minting fails (older backend, network
 *  blip); with no token stored, the URL goes out unmodified. */
export async function ticketed(url: string): Promise<string> {
  const token = getToken();
  if (!token) return url;
  try {
    const r = await apiFetch("/api/auth/ticket", { method: "POST" });
    if (r.ok) {
      const { ticket } = await r.json();
      if (ticket) return `${url}${url.includes("?") ? "&" : "?"}ticket=${encodeURIComponent(ticket)}`;
    }
  } catch {
    /* fall through to token */
  }
  return tokenized(url);
}
