import type { Portfolio, PriceUpdate, WatchlistItem } from "@/lib/types";

export function tick(ticker: string, price: number, prev = price, open = prev, ts = Date.now() / 1000): PriceUpdate {
  return {
    ticker,
    price,
    previous_price: prev,
    timestamp: ts,
    change: price - prev,
    change_percent: prev ? ((price - prev) / prev) * 100 : 0,
    direction: price > prev ? "up" : price < prev ? "down" : "flat",
    session_open: open,
    session_change_percent: open ? ((price - open) / open) * 100 : 0,
  };
}

export const portfolioFixture: Portfolio = {
  cash_balance: 8000,
  positions_value: 2000,
  total_value: 10000,
  unrealized_pnl: 100,
  positions: [
    {
      ticker: "AAPL",
      quantity: 10,
      avg_cost: 190,
      current_price: 200,
      market_value: 2000,
      unrealized_pnl: 100,
      unrealized_pnl_percent: 5.263,
    },
  ],
};

export const watchlistFixture: WatchlistItem[] = [
  { ticker: "AAPL", price: 200, previous_price: 199, session_change_percent: 1.2, added_at: "2026-11-16T14:00:00Z" },
  { ticker: "MSFT", price: null, previous_price: null, session_change_percent: null, added_at: "2026-11-16T14:00:01Z" },
];

/** Install a fetch mock routing by "METHOD path". Handlers return [status, body]. */
export function mockFetch(routes: Record<string, (body: unknown) => [number, unknown]>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const fn = async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    const handler = routes[`${method} ${path}`];
    const [status, resBody] = handler ? handler(body) : [404, { detail: "Not Found" }];
    return new Response(status === 204 ? null : JSON.stringify(resBody), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  };
  globalThis.fetch = fn as typeof fetch;
  return calls;
}
