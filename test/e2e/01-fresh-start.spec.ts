import { expect, test } from '@playwright/test';
import { DEFAULT_TICKERS, expectPricesToTick, getPortfolio, getWatchlist, moneyOf, openApp } from './helpers';

// Must run first, against a freshly created database.
test.describe('fresh start', () => {
  test('health endpoint is up', async ({ request }) => {
    const res = await request.get('/api/health');
    expect(res.status()).toBe(200);
    expect(await res.json()).toEqual({ status: 'ok' });
  });

  test('API starts with the seeded state', async ({ request }) => {
    const portfolio = await getPortfolio(request);
    expect(portfolio.cash_balance).toBe(10000);
    expect(portfolio.positions).toEqual([]);
    expect(portfolio.total_value).toBe(10000);

    const watchlist = await getWatchlist(request);
    expect(watchlist.map((w) => w.ticker)).toEqual(DEFAULT_TICKERS);
  });

  test('shows the default watchlist, $10k cash and empty states', async ({ page }) => {
    await openApp(page);

    for (const ticker of DEFAULT_TICKERS) {
      await expect(page.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();
    }
    await expect(page.getByTestId(/^watchlist-row-/)).toHaveCount(DEFAULT_TICKERS.length);

    await expect(page.getByTestId('cash-balance')).toContainText('10,000.00');
    expect(await moneyOf(page.getByTestId('total-value'))).toBeCloseTo(10000, 0);

    await expect(page.getByTestId('positions-empty')).toBeVisible();
    await expect(page.getByTestId('heatmap-empty')).toBeVisible();
  });

  test('prices are streaming', async ({ page }) => {
    await openApp(page);
    await expect(page.getByTestId('connection-status')).toHaveAttribute('data-status', 'connected');
    // Every default ticker eventually shows a numeric price.
    for (const ticker of DEFAULT_TICKERS) {
      await expect(page.getByTestId(`watchlist-price-${ticker}`)).toHaveText(/\d+\.\d{2}/);
    }
    await expectPricesToTick(page);
  });

  test('SSE endpoint emits batched price events', async ({ page }) => {
    await page.goto('/');
    const result = await page.evaluate(async () => {
      const controller = new AbortController();
      const res = await fetch('/api/stream/prices', { signal: controller.signal });
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let text = '';
      const deadline = Date.now() + 10_000;
      while (Date.now() < deadline) {
        const { value, done } = await reader.read();
        if (done) break;
        text += decoder.decode(value, { stream: true });
        if (/data: .*\n\n/.test(text)) break;
      }
      controller.abort();
      return { contentType: res.headers.get('content-type'), text };
    });
    expect(result.contentType).toContain('text/event-stream');
    expect(result.text).toContain('retry: 1000');
    const dataLine = result.text.split('\n').find((l) => l.startsWith('data: '));
    expect(dataLine, 'no data event received').toBeTruthy();
    const batch = JSON.parse(dataLine!.slice('data: '.length));
    expect(Object.keys(batch)).toEqual(expect.arrayContaining(DEFAULT_TICKERS));
    const aapl = batch.AAPL;
    expect(aapl).toMatchObject({ ticker: 'AAPL' });
    for (const key of ['price', 'previous_price', 'timestamp', 'change', 'change_percent', 'session_open', 'session_change_percent']) {
      expect(typeof aapl[key], key).toBe('number');
    }
    expect(['up', 'down', 'flat']).toContain(aapl.direction);
  });
});
