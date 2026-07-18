/** lib/api.ts: bearer injection, the 401 event bus, and ticketed URLs —
 *  the auth layer everything else rides on (H3b). */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  apiFetch,
  getToken,
  portfolioQuery,
  setToken,
  ticketed,
  UNAUTHORIZED_EVENT,
} from "@/lib/api";

const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
});

describe("apiFetch", () => {
  it("passes through untouched with no token stored", async () => {
    fetchMock.mockResolvedValue(new Response("{}"));
    await apiFetch("/api/orders");
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
  });

  it("injects the stored bearer token", async () => {
    setToken("secret-1");
    fetchMock.mockResolvedValue(new Response("{}"));
    await apiFetch("/api/orders");
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer secret-1");
  });

  it("fires the unauthorized event on a 401", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 401 }));
    const seen = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, seen);
    await apiFetch("/api/orders");
    expect(seen).toHaveBeenCalledTimes(1);
    window.removeEventListener(UNAUTHORIZED_EVENT, seen);
  });
});

describe("token storage", () => {
  it("round-trips and clears", () => {
    setToken("abc");
    expect(getToken()).toBe("abc");
    setToken("");
    expect(getToken()).toBe("");
  });
});

describe("ticketed", () => {
  it("returns the url unmodified with no token", async () => {
    expect(await ticketed("/api/agents/run/stream")).toBe("/api/agents/run/stream");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("appends a minted single-use ticket", async () => {
    setToken("secret-1");
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ticket: "tick-9" }), { status: 200 }),
    );
    expect(await ticketed("/api/x")).toBe("/api/x?ticket=tick-9");
  });

  it("falls back to ?token= if minting fails", async () => {
    setToken("secret-1");
    fetchMock.mockRejectedValue(new TypeError("offline"));
    expect(await ticketed("/api/x")).toBe("/api/x?token=secret-1");
  });
});

describe("portfolioQuery", () => {
  it("is empty for the default portfolio and filters otherwise", () => {
    expect(portfolioQuery("default")).toBe("");
    expect(portfolioQuery("p 1")).toBe("?portfolio_id=p%201");
  });
});
