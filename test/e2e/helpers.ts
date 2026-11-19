import { APIRequestContext, Locator, Page, expect } from '@playwright/test';

export const DEFAULT_TICKERS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'];

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
}

export interface Portfolio {
  cash_balance: number;
  positions_value: number;
  total_value: number;
  unrealized_pnl: number;
  positions: Position[];
}

export interface WatchlistItem {
  ticker: string;
  price: number | null;
  previous_price: number | null;
  session_change_percent: number | null;
  added_at: string;
}

/** Parse "$10,054.95", "-$12.30", "(12.30)" or "1,234.5" into a number. */
export function parseMoney(text: string | null): number {
  if (!text) return NaN;
  const negative = /-|\(/.test(text);
  const cleaned = text.replace(/[^0-9.]/g, '');
  const n = parseFloat(cleaned);
  return negative ? -n : n;
}

export async function getPortfolio(request: APIRequestContext): Promise<Portfolio> {
  const res = await request.get('/api/portfolio');
  expect(res.status()).toBe(200);
  return res.json();
}

export async function getWatchlist(request: APIRequestContext): Promise<WatchlistItem[]> {
  const res = await request.get('/api/watchlist');
  expect(res.status()).toBe(200);
  return res.json();
}

export function positionQty(p: Portfolio, ticker: string): number {
  return p.positions.find((x) => x.ticker === ticker)?.quantity ?? 0;
}

/** Wait until the backend has a cached price for the ticker (needed before trading). */
export async function waitForPrice(request: APIRequestContext, ticker: string): Promise<void> {
  await expect
    .poll(async () => (await getWatchlist(request)).find((w) => w.ticker === ticker)?.price ?? null, {
      message: `price for ${ticker} never arrived`,
      timeout: 20_000,
    })
    .not.toBeNull();
}

/** Execute a trade through the API (setup helper, not under test). */
export async function apiTrade(
  request: APIRequestContext,
  ticker: string,
  side: 'buy' | 'sell',
  quantity: number,
): Promise<void> {
  const res = await request.post('/api/portfolio/trade', { data: { ticker, side, quantity } });
  expect(res.status(), await res.text()).toBe(200);
}

/** Open the app and wait until the watchlist is rendered with live prices. */
export async function openApp(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.getByTestId('watchlist')).toBeVisible();
  await expect(page.getByTestId(/^watchlist-row-/).first()).toBeVisible();
  await expect(page.getByTestId('connection-status')).toHaveAttribute('data-status', 'connected', { timeout: 15_000 });
}

/** Text snapshot of every price cell in the watchlist. */
export async function priceSnapshot(page: Page): Promise<string[]> {
  return page.getByTestId(/^watchlist-price-/).allTextContents();
}

/** Resolves once any watchlist price cell changes its text (prices are streaming). */
export async function expectPricesToTick(page: Page, timeout = 15_000): Promise<void> {
  const before = (await priceSnapshot(page)).join('|');
  await expect.poll(async () => (await priceSnapshot(page)).join('|'), { timeout, message: 'prices did not update' }).not.toBe(before);
}

export async function fillTrade(page: Page, ticker: string, quantity: number | string): Promise<void> {
  await page.getByTestId('trade-ticker').fill(ticker);
  await page.getByTestId('trade-quantity').fill(String(quantity));
}

export async function moneyOf(locator: Locator): Promise<number> {
  return parseMoney(await locator.textContent());
}
