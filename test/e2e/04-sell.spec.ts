import { expect, test } from '@playwright/test';
import { apiTrade, fillTrade, getPortfolio, openApp, positionQty, waitForPrice } from './helpers';

const TICKER = 'MSFT';

test.describe('sell', () => {
  test.beforeEach(async ({ request }) => {
    await waitForPrice(request, TICKER);
    // Start from exactly 3 shares of MSFT.
    const held = positionQty(await getPortfolio(request), TICKER);
    if (held > 0) await apiTrade(request, TICKER, 'sell', held);
    await apiTrade(request, TICKER, 'buy', 3);
  });

  test('partial sell raises cash and reduces the position; selling the rest removes it', async ({ page, request }) => {
    const before = await getPortfolio(request);
    expect(positionQty(before, TICKER)).toBeCloseTo(3, 4);

    await openApp(page);
    await expect(page.getByTestId(`position-row-${TICKER}`)).toBeVisible();

    // Partial sell
    await fillTrade(page, TICKER, 1);
    await page.getByTestId('trade-sell').click();
    await expect.poll(async () => positionQty(await getPortfolio(request), TICKER)).toBeCloseTo(2, 4);
    const mid = await getPortfolio(request);
    expect(mid.cash_balance).toBeGreaterThan(before.cash_balance);
    await expect(page.getByTestId(`position-row-${TICKER}`)).toBeVisible();
    await expect(page.getByTestId('trade-error')).toHaveCount(0);

    // Sell the remainder: the position row disappears
    await fillTrade(page, TICKER, 2);
    await page.getByTestId('trade-sell').click();
    await expect(page.getByTestId(`position-row-${TICKER}`)).toHaveCount(0);
    const after = await getPortfolio(request);
    expect(positionQty(after, TICKER)).toBe(0);
    expect(after.cash_balance).toBeGreaterThan(mid.cash_balance);
  });

  test('selling more than held shows an inline error', async ({ page, request }) => {
    const before = await getPortfolio(request);
    await openApp(page);

    await fillTrade(page, TICKER, 100);
    await page.getByTestId('trade-sell').click();
    await expect(page.getByTestId('trade-error')).toBeVisible();
    await expect(page.getByTestId('trade-error')).toContainText(/insufficient shares|you hold|only hold|not enough/i);

    const after = await getPortfolio(request);
    expect(positionQty(after, TICKER)).toBeCloseTo(positionQty(before, TICKER), 4);
    expect(after.cash_balance).toBe(before.cash_balance);
  });

  test.afterAll(async ({ request }) => {
    const held = positionQty(await getPortfolio(request), TICKER);
    if (held > 0) await apiTrade(request, TICKER, 'sell', held);
  });
});
