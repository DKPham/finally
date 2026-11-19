import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import Workstation from "./Workstation";
import { MockEventSource } from "@/test/mockEventSource";
import { mockFetch, portfolioFixture, tick, watchlistFixture } from "@/test/fixtures";
import type { Portfolio } from "@/lib/types";

function routes(overrides: Record<string, (b: unknown) => [number, unknown]> = {}) {
  return mockFetch({
    "GET /api/portfolio": () => [200, portfolioFixture],
    "GET /api/watchlist": () => [200, watchlistFixture],
    "GET /api/portfolio/history": () => [200, [{ recorded_at: "2026-11-16T14:03:00Z", total_value: 10000 }]],
    "GET /api/chat/history": () => [200, []],
    ...overrides,
  });
}

describe("Workstation", () => {
  it("loads data and revalues the portfolio live from SSE", async () => {
    routes();
    render(<Workstation />);
    expect(await screen.findByTestId("watchlist-row-AAPL")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("total-value")).toHaveTextContent("$10,000.00"));
    expect(screen.getByTestId("cash-balance")).toHaveTextContent("$8,000.00");
    expect(MockEventSource.instances).toHaveLength(1);

    act(() => {
      MockEventSource.latest().open();
      MockEventSource.latest().emit({ AAPL: tick("AAPL", 210, 200, 200), MSFT: tick("MSFT", 400) });
    });
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
    expect(screen.getByTestId("total-value")).toHaveTextContent("$10,100.00");
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveTextContent("210.00");
    expect(screen.getByTestId("position-price-AAPL")).toHaveTextContent("210.00");
    // defaults selection to the first watchlist ticker
    expect(screen.getByTestId("main-chart-ticker")).toHaveTextContent("AAPL");
    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-ticker", "AAPL");
  });

  it("executes a trade and refreshes portfolio, history and watchlist", async () => {
    const after: Portfolio = { ...portfolioFixture, cash_balance: 7000, positions: [] };
    const calls = routes({
      "POST /api/portfolio/trade": () => [
        200,
        {
          trade: { id: "x", ticker: "AAPL", side: "buy", quantity: 5, price: 200, executed_at: "" },
          portfolio: after,
        },
      ],
    });
    render(<Workstation />);
    await screen.findByTestId("watchlist-row-AAPL");
    await waitFor(() => expect(screen.getByTestId("trade-ticker")).toHaveValue("AAPL"));
    await userEvent.type(screen.getByTestId("trade-quantity"), "5");
    await userEvent.click(screen.getByTestId("trade-buy"));
    await waitFor(() => expect(screen.getByTestId("cash-balance")).toHaveTextContent("$7,000.00"));
    const trade = calls.find((c) => c.method === "POST");
    expect(trade?.body).toEqual({ ticker: "AAPL", quantity: 5, side: "buy" });
    await waitFor(() =>
      expect(calls.filter((c) => c.path === "/api/portfolio/history").length).toBeGreaterThanOrEqual(2),
    );
    expect(screen.getByTestId("positions-empty")).toBeInTheDocument();
  });

  it("sends a chat message, renders actions, and refetches after actions", async () => {
    let chatDone = false;
    const calls = routes({
      "POST /api/chat": () => {
        chatDone = true;
        return [
          200,
          {
            message: "Buying 1 AAPL.",
            actions: [
              { type: "trade", ticker: "AAPL", side: "buy", quantity: 1, status: "executed", price: 200, error: null },
            ],
          },
        ];
      },
    });
    render(<Workstation />);
    await screen.findByTestId("watchlist-row-AAPL");
    const before = calls.filter((c) => c.path === "/api/portfolio").length;
    await userEvent.type(screen.getByTestId("chat-input"), "buy 1 AAPL{enter}");
    expect(await screen.findByText("Buying 1 AAPL.")).toBeInTheDocument();
    expect(chatDone).toBe(true);
    expect(screen.getByTestId("chat-action")).toHaveTextContent("Bought 1 AAPL @ $200.00");
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/portfolio").length).toBe(before + 1));
    expect(screen.queryByTestId("chat-loading")).not.toBeInTheDocument();
  });

  it("removes a ticker from the watchlist", async () => {
    let list = watchlistFixture;
    routes({
      "GET /api/watchlist": () => [200, list],
      "DELETE /api/watchlist/MSFT": () => {
        list = list.filter((i) => i.ticker !== "MSFT");
        return [204, null];
      },
    });
    render(<Workstation />);
    await userEvent.click(await screen.findByTestId("watchlist-remove-MSFT"));
    await waitFor(() => expect(screen.queryByTestId("watchlist-row-MSFT")).not.toBeInTheDocument());
  });
});
