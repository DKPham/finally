import { expect, test } from '@playwright/test';
import { fillTrade, getPortfolio, moneyOf, openApp, positionQty, waitForPrice } from './helpers';

test.describe('buy', () => {
  test('buying shares lowers cash and shows the position', async ({ page, request }) => {
    await waitForPrice(request, 'AAPL');
    const before = await getPortfolio(request);
    await openApp(page);
    const headerCashBefore = await moneyOf(page.getByTestId('cash-balance'));
    expect(headerCashBefore).toBeCloseTo(before.cash_balance, 2);

    await fillTrade(page, 'AAPL', 2);
    await page.getByTestId('trade-buy').click();

    await expect(page.getByTestId('position-row-AAPL')).toBeVisible();
    await expect(page.getByTestId('trade-error')).toHaveCount(0);

    await expect.poll(async () => positionQty(await getPortfolio(request), 'AAPL')).toBeCloseTo(positionQty(before, 'AAPL') + 2, 4);
    const after = await getPortfolio(request);
    expect(after.cash_balance).toBeLessThan(before.cash_balance);

    // Header cash reflects the new balance
    await expect.poll(async () => moneyOf(page.getByTestId('cash-balance'))).toBeCloseTo(after.cash_balance, 2);
    await expect(page.getByTestId('positions-empty')).toHaveCount(0);
    await expect(page.getByTestId('position-row-AAPL')).toContainText('AAPL');
  });

  test('buying with insufficient cash shows an inline error', async ({ page, request }) => {
    await waitForPrice(request, 'NVDA');
    const before = await getPortfolio(request);
    await openApp(page);

    await fillTrade(page, 'NVDA', 1_000_000);
    await page.getByTestId('trade-buy').click();

    await expect(page.getByTestId('trade-error')).toBeVisible();
    await expect(page.getByTestId('trade-error')).toContainText(/insufficient cash/i);

    const after = await getPortfolio(request);
    expect(after.cash_balance).toBe(before.cash_balance);
    expect(positionQty(after, 'NVDA')).toBe(positionQty(before, 'NVDA'));
  });

  test('trade API validates requests', async ({ request }) => {
    let res = await request.post('/api/portfolio/trade', { data: { ticker: 'AAPL', side: 'buy', quantity: 0 } });
    expect([400, 422]).toContain(res.status());
    res = await request.post('/api/portfolio/trade', { data: { ticker: 'AAPL', side: 'hold', quantity: 1 } });
    expect(res.status()).toBe(422);
    res = await request.post('/api/portfolio/trade', { data: { ticker: 'AAPL', side: 'buy', quantity: 1_000_000 } });
    expect(res.status()).toBe(400);
    expect((await res.json()).detail).toMatch(/insufficient cash/i);
  });
});
