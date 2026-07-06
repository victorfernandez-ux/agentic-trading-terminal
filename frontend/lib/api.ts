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

/** Append ?token= (or &token=) to a URL for header-less clients (SSE/WS). */
export function tokenized(url: string): string {
  const token = getToken();
  if (!token) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
}
