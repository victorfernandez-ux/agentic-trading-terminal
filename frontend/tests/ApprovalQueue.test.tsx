/** Pins the approval gate's UI behavior (H2/H3b): failures are loud,
 *  double-clicks are locked out, approve requires a confirm step, and the
 *  queue re-syncs to the server's state after every action. */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ApprovalQueue from "@/components/ApprovalQueue";
import type { Order } from "@/lib/types";

const PENDING: Order = {
  id: "ord_1",
  symbol: "NVDA",
  side: "buy",
  qty: 3,
  order_type: "market",
  status: "PENDING_APPROVAL",
  est_notional: 1500,
  est_price: 500,
  created_ts: Date.now() - 60_000,
  thesis: "Breakout above the 50-day with volume.",
  source: "agent",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

function mockQueue(orders: Order[]) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") throw new Error(`unexpected POST ${url}`);
    return jsonResponse(orders);
  });
}

async function approveFlow(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Approve" }));
  await user.click(await screen.findByRole("button", { name: "Confirm" }));
}

describe("ApprovalQueue", () => {
  it("renders order detail the approver needs: price, age, thesis", async () => {
    mockQueue([PENDING]);
    render(<ApprovalQueue refreshKey={0} />);
    expect(await screen.findByText(/NVDA/)).toBeInTheDocument();
    expect(screen.getByText(/est \$500/)).toBeInTheDocument();
    expect(screen.getByText(/proposed 1m ago/)).toBeInTheDocument();
    expect(screen.getByText(/Breakout above the 50-day/)).toBeInTheDocument();
  });

  it("approve is two-step and hits the API only on confirm", async () => {
    const user = userEvent.setup();
    const posts: string[] = [];
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posts.push(url);
        return jsonResponse({ ...PENDING, status: "SUBMITTED" });
      }
      return jsonResponse([PENDING]);
    });
    render(<ApprovalQueue refreshKey={0} />);
    await user.click(await screen.findByRole("button", { name: "Approve" }));
    expect(posts).toHaveLength(0); // armed, not fired
    expect(screen.getByText(/Confirm BUY 3 NVDA/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(posts).toEqual(["/api/orders/ord_1/approve"]));
  });

  it("cancel disarms without calling the API", async () => {
    const user = userEvent.setup();
    mockQueue([PENDING]);
    render(<ApprovalQueue refreshKey={0} />);
    await user.click(await screen.findByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== "POST")).toBe(true);
  });

  it("surfaces a 409 as an error and re-syncs to the server's state", async () => {
    const user = userEvent.setup();
    let resolved = false;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        resolved = true;
        return jsonResponse(
          { detail: "order is SUBMITTED", error: { code: 409, message: "order is SUBMITTED" } },
          409,
        );
      }
      return jsonResponse([resolved ? { ...PENDING, status: "SUBMITTED" } : PENDING]);
    });
    render(<ApprovalQueue refreshKey={0} />);
    await approveFlow(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/approve failed: order is SUBMITTED/);
    // reload after the 409 shows the real status and removes the buttons
    expect(await screen.findByText("SUBMITTED")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("surfaces a network failure as NOT approved", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") throw new TypeError("network down");
      return jsonResponse([PENDING]);
    });
    render(<ApprovalQueue refreshKey={0} />);
    await approveFlow(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/NOT approved/);
  });

  it("keeps the last-known queue with a banner when a refresh fails", async () => {
    let fail = false;
    fetchMock.mockImplementation(async () => {
      if (fail) throw new TypeError("offline");
      return jsonResponse([PENDING]);
    });
    const { rerender } = render(<ApprovalQueue refreshKey={0} />);
    expect(await screen.findByText(/NVDA/)).toBeInTheDocument();
    fail = true;
    rerender(<ApprovalQueue refreshKey={1} />); // force a reload that fails
    expect(await screen.findByText(/Queue refresh failed/)).toBeInTheDocument();
    expect(screen.getByText(/NVDA/)).toBeInTheDocument(); // data kept
  });
});
