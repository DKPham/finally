import { expect, test } from '@playwright/test';
import { getPortfolio, getWatchlist, openApp, positionQty, waitForPrice } from './helpers';

// Requires the backend to run with LLM_MOCK=true.
test.describe('AI chat (mocked LLM)', () => {
  test('"buy 1 AAPL" executes a trade shown inline and the position appears', async ({ page, request }) => {
    await waitForPrice(request, 'AAPL');
    const before = await getPortfolio(request);
    await openApp(page);

    await expect(page.getByTestId('chat-panel')).toBeVisible();
    await page.getByTestId('chat-input').fill('buy 1 AAPL');
    await page.getByTestId('chat-send').click();

    const userMsg = page.locator('[data-testid="chat-message"][data-role="user"]', { hasText: 'buy 1 AAPL' });
    await expect(userMsg.last()).toBeVisible();

    const reply = page.locator('[data-testid="chat-message"][data-role="assistant"]', { hasText: 'Buying 1 AAPL.' }).last();
    await expect(reply).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('chat-loading')).toHaveCount(0);

    const action = reply.getByTestId('chat-action');
    await expect(action).toHaveCount(1);
    await expect(action).toHaveAttribute('data-status', 'executed');
    await expect(action).toContainText('AAPL');
    await expect(action).toContainText('✓');

    await expect(page.getByTestId('position-row-AAPL')).toBeVisible();
    await expect.poll(async () => positionQty(await getPortfolio(request), 'AAPL')).toBeCloseTo(positionQty(before, 'AAPL') + 1, 4);

    // The conversation survives a reload
    await page.reload();
    await expect(
      page.locator('[data-testid="chat-message"][data-role="assistant"]', { hasText: 'Buying 1 AAPL.' }).last(),
    ).toBeVisible();
  });

  test('a failed action is shown inline as a failure', async ({ page, request }) => {
    const held = positionQty(await getPortfolio(request), 'TSLA');
    await openApp(page);
    await page.getByTestId('chat-input').fill(`sell ${Math.floor(held) + 100} TSLA`);
    await page.getByTestId('chat-send').click();

    const reply = page.locator('[data-testid="chat-message"][data-role="assistant"]', { hasText: /Selling [\d.]+ TSLA\./ }).last();
    await expect(reply).toBeVisible({ timeout: 20_000 });
    const action = reply.getByTestId('chat-action');
    await expect(action).toHaveAttribute('data-status', 'failed');
    await expect(action).toContainText('✗');
    expect(positionQty(await getPortfolio(request), 'TSLA')).toBe(held);
  });

  test('chat can manage the watchlist', async ({ page, request }) => {
    if ((await getWatchlist(request)).some((w) => w.ticker === 'ORCL')) await request.delete('/api/watchlist/ORCL');
    await openApp(page);

    await page.getByTestId('chat-input').fill('watch ORCL');
    await page.getByTestId('chat-send').click();
    await expect(page.locator('[data-testid="chat-message"][data-role="assistant"]', { hasText: 'Adding ORCL to your watchlist.' }).last()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('watchlist-row-ORCL')).toBeVisible();

    await page.getByTestId('chat-input').fill('unwatch ORCL');
    await page.getByTestId('chat-send').click();
    await expect(page.locator('[data-testid="chat-message"][data-role="assistant"]', { hasText: 'Removing ORCL from your watchlist.' }).last()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('watchlist-row-ORCL')).toHaveCount(0);
  });

  test('chat API returns the documented shape', async ({ request }) => {
    const res = await request.post('/api/chat', { data: { message: 'hello there' } });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ message: 'This is a mock response from FinAlly.', actions: [] });

    const hist = await request.get('/api/chat/history');
    expect(hist.status()).toBe(200);
    const messages = await hist.json();
    expect(messages.length).toBeLessThanOrEqual(50);
    const last = messages[messages.length - 1];
    expect(last).toMatchObject({ role: 'assistant', content: 'This is a mock response from FinAlly.' });
    expect(messages[messages.length - 2]).toMatchObject({ role: 'user', content: 'hello there', actions: null });
  });
});
