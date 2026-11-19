import { Page, Route, expect, test } from '@playwright/test';
import { expectPricesToTick, getWatchlist } from './helpers';

/*
 * Chromium's offline emulation does not tear down an already-open SSE stream,
 * so these tests drop the connection deterministically with request routing:
 * the first /api/stream/prices request is answered with a *finite* SSE body
 * (one real-looking batch, then EOF). EventSource sees the stream end exactly
 * as it would if the server went away, and reconnects on its own.
 */

const STREAM = '**/api/stream/prices';

/** Record every data-status value the connection indicator takes, from page load. */
async function recordStatusHistory(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { __statusHistory: string[] };
    w.__statusHistory = [];
    const push = (v: string | null) => {
      if (v && w.__statusHistory[w.__statusHistory.length - 1] !== v) w.__statusHistory.push(v);
    };
    new MutationObserver(() => {
      push(document.querySelector('[data-testid="connection-status"]')?.getAttribute('data-status') ?? null);
    }).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-status'] });
  });
}

const statusHistory = (page: Page) => page.evaluate(() => (window as unknown as { __statusHistory: string[] }).__statusHistory);

/** A one-shot SSE response built from the real current prices. */
async function finiteStreamBody(request: import('@playwright/test').APIRequestContext): Promise<string> {
  const batch: Record<string, unknown> = {};
  for (const w of await getWatchlist(request)) {
    if (w.price === null) continue;
    batch[w.ticker] = {
      ticker: w.ticker,
      price: w.price,
      previous_price: w.previous_price ?? w.price,
      timestamp: Date.now() / 1000,
      change: 0,
      change_percent: 0,
      direction: 'flat',
      session_open: w.price,
      session_change_percent: w.session_change_percent ?? 0,
    };
  }
  return `retry: 1000\n\ndata: ${JSON.stringify(batch)}\n\n`;
}

const fulfillFinite = (route: Route, body: string) =>
  route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' }, body });

test.describe('SSE resilience', () => {
  test('reconnects automatically after the stream drops', async ({ page, request }) => {
    await recordStatusHistory(page);
    const body = await finiteStreamBody(request);
    let streamRequests = 0;
    await page.route(STREAM, async (route) => {
      streamRequests += 1;
      if (streamRequests === 1) return fulfillFinite(route, body); // connects, then drops
      return route.continue(); // real, long-lived stream
    });

    await page.goto('/');
    await expect(page.getByTestId('connection-status')).toHaveAttribute('data-status', 'connected', { timeout: 15_000 });
    await expect.poll(() => streamRequests, { message: 'EventSource never reconnected' }).toBeGreaterThanOrEqual(2);
    await expect(page.getByTestId('connection-status')).toHaveAttribute('data-status', 'connected', { timeout: 15_000 });
    await expectPricesToTick(page);

    const history = await statusHistory(page);
    const firstConnected = history.indexOf('connected');
    expect(firstConnected, `history: ${history.join(' > ')}`).toBeGreaterThanOrEqual(0);
    expect(history.slice(firstConnected + 1), `history: ${history.join(' > ')}`).toContain('reconnecting');
    expect(history[history.length - 1]).toBe('connected');
  });

  test('goes yellow then red while the server is unreachable, and recovers', async ({ page, request }) => {
    await recordStatusHistory(page);
    const body = await finiteStreamBody(request);
    let streamRequests = 0;
    await page.route(STREAM, async (route) => {
      streamRequests += 1;
      if (streamRequests === 1) return fulfillFinite(route, body); // connects, then drops
      return route.abort('connectionrefused'); // server is gone
    });

    await page.goto('/');
    await expect.poll(() => streamRequests).toBeGreaterThanOrEqual(2);
    await expect(page.getByTestId('connection-status')).toHaveAttribute('data-status', 'disconnected', { timeout: 20_000 });

    const history = await statusHistory(page);
    expect(history, `history: ${history.join(' > ')}`).toEqual(expect.arrayContaining(['connected', 'reconnecting', 'disconnected']));
    expect(history.indexOf('reconnecting', history.indexOf('connected'))).toBeLessThan(history.lastIndexOf('disconnected'));

    // Server comes back
    await page.unroute(STREAM);
    await expect(page.getByTestId('connection-status')).toHaveAttribute('data-status', 'connected', { timeout: 20_000 });
    await expectPricesToTick(page);
  });
});
