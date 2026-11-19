import { expect, test } from '@playwright/test';
import { getWatchlist, openApp } from './helpers';

const TICKER = 'PYPL';

test.describe('watchlist', () => {
  test.beforeEach(async ({ request }) => {
    // Make the spec re-runnable: start with PYPL not on the watchlist.
    if ((await getWatchlist(request)).some((w) => w.ticker === TICKER)) {
      await request.delete(`/api/watchlist/${TICKER}`);
    }
  });

  test('add a ticker, see it stream, then remove it', async ({ page, request }) => {
    await openApp(page);
    await expect(page.getByTestId(`watchlist-row-${TICKER}`)).toHaveCount(0);

    // Add (lowercase input: the backend normalizes to uppercase)
    await page.getByTestId('watchlist-add-input').fill(TICKER.toLowerCase());
    await page.getByTestId('watchlist-add-button').click();

    const row = page.getByTestId(`watchlist-row-${TICKER}`);
    await expect(row).toBeVisible();
    await expect(page.getByTestId(`watchlist-price-${TICKER}`)).toHaveText(/\d+\.\d{2}/, { timeout: 20_000 });
    expect((await getWatchlist(request)).map((w) => w.ticker)).toContain(TICKER);

    // Survives a reload
    await page.reload();
    await expect(page.getByTestId(`watchlist-row-${TICKER}`)).toBeVisible();

    // Remove
    await page.getByTestId(`watchlist-remove-${TICKER}`).click();
    await expect(page.getByTestId(`watchlist-row-${TICKER}`)).toHaveCount(0);
    expect((await getWatchlist(request)).map((w) => w.ticker)).not.toContain(TICKER);

    await page.reload();
    await expect(page.getByTestId('watchlist-row-AAPL')).toBeVisible();
    await expect(page.getByTestId(`watchlist-row-${TICKER}`)).toHaveCount(0);
  });

  test('API status codes for watchlist changes', async ({ request }) => {
    let res = await request.post('/api/watchlist', { data: { ticker: TICKER.toLowerCase() } });
    expect(res.status()).toBe(201);
    expect((await res.json()).ticker).toBe(TICKER);

    res = await request.post('/api/watchlist', { data: { ticker: TICKER } });
    expect(res.status()).toBe(409);
    expect(typeof (await res.json()).detail).toBe('string');

    res = await request.post('/api/watchlist', { data: { ticker: '123!' } });
    expect(res.status()).toBe(422);

    res = await request.delete(`/api/watchlist/${TICKER}`);
    expect(res.status()).toBe(204);

    res = await request.delete(`/api/watchlist/${TICKER}`);
    expect(res.status()).toBe(404);
  });

  test('clicking a ticker selects it in the main chart', async ({ page }) => {
    await openApp(page);
    await page.getByTestId('watchlist-row-MSFT').click();
    await expect(page.getByTestId('main-chart')).toHaveAttribute('data-ticker', 'MSFT');
    await page.getByTestId('watchlist-row-AAPL').click();
    await expect(page.getByTestId('main-chart')).toHaveAttribute('data-ticker', 'AAPL');
  });
});
