import { Locator, expect, test } from '@playwright/test';
import { apiTrade, getPortfolio, openApp, positionQty, waitForPrice } from './helpers';

const TICKERS = ['JPM', 'V'];

/** Fill colour of a heatmap cell as [r, g, b]. Looks at the cell itself or its first rect. */
async function cellRgb(cell: Locator): Promise<[number, number, number]> {
  return cell.evaluate((el) => {
    const target = el.tagName.toLowerCase() === 'rect' ? el : el.querySelector('rect') ?? el;
    const style = getComputedStyle(target as Element);
    let color = (target as Element).getAttribute('fill') || style.fill;
    if (!color || color === 'none') color = style.backgroundColor;
    // Normalise any CSS colour to rgb() via a probe element.
    const probe = document.createElement('div');
    probe.style.color = color;
    document.body.appendChild(probe);
    const rgb = getComputedStyle(probe).color;
    probe.remove();
    const m = rgb.match(/\d+(\.\d+)?/g)!.map(Number);
    return [m[0], m[1], m[2]] as [number, number, number];
  });
}

test.describe('portfolio visualizations', () => {
  test.beforeAll(async ({ request }) => {
    for (const t of TICKERS) {
      await waitForPrice(request, t);
      if (positionQty(await getPortfolio(request), t) === 0) await apiTrade(request, t, 'buy', 5);
    }
  });

  test('heatmap renders a cell per position, coloured by P&L', async ({ page, request }) => {
    await openApp(page);
    const heatmap = page.getByTestId('heatmap');
    await expect(heatmap).toBeVisible();
    await expect(page.getByTestId('heatmap-empty')).toHaveCount(0);

    const portfolio = await getPortfolio(request);
    for (const pos of portfolio.positions) {
      await expect(page.getByTestId(`heatmap-cell-${pos.ticker}`)).toBeVisible();
    }

    for (const ticker of TICKERS) {
      const cell = page.getByTestId(`heatmap-cell-${ticker}`);
      // Sample colour and P&L together; prices move, so retry until they agree in one render.
      await expect
        .poll(
          async () => {
            const attr = await cell.getAttribute('data-pnl');
            const pnl = attr !== null ? Number(attr) : (await getPortfolio(request)).positions.find((p) => p.ticker === ticker)!.unrealized_pnl_percent;
            const [r, g] = await cellRgb(cell);
            if (Math.abs(pnl) < 0.005) return 'flat';
            const colourSign = g > r ? 'green' : r > g ? 'red' : 'neutral';
            return (pnl > 0 ? 'green' : 'red') === colourSign ? 'consistent' : `pnl=${pnl} colour=${colourSign}`;
          },
          { timeout: 15_000, message: `heatmap colour for ${ticker} does not match its P&L sign` },
        )
        .toMatch(/consistent|flat/);
    }
  });

  test('P&L chart has data points', async ({ page, request }) => {
    const res = await request.get('/api/portfolio/history');
    expect(res.status()).toBe(200);
    const history: { recorded_at: string; total_value: number }[] = await res.json();
    // Startup snapshot plus one after each trade
    expect(history.length).toBeGreaterThanOrEqual(2);
    for (const h of history) {
      expect(typeof h.total_value).toBe('number');
      expect(h.recorded_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/);
    }
    const times = history.map((h) => Date.parse(h.recorded_at));
    expect([...times].sort((a, b) => a - b)).toEqual(times);

    await openApp(page);
    const chart = page.getByTestId('pnl-chart');
    await expect(chart).toBeVisible();
    const line = chart.locator('path.recharts-line-curve, path.recharts-area-curve').first();
    await expect(line).toBeAttached();
    await expect.poll(async () => ((await line.getAttribute('d')) ?? '').length).toBeGreaterThan(10);
  });

  test('positions table shows the required columns', async ({ page, request }) => {
    await openApp(page);
    const table = page.getByTestId('positions-table');
    await expect(table).toBeVisible();
    for (const header of [/ticker/i, /qty|quantity/i, /avg/i, /price/i, /p&l|pnl/i, /%/]) {
      await expect(table).toContainText(header);
    }
    const portfolio = await getPortfolio(request);
    for (const pos of portfolio.positions) {
      await expect(page.getByTestId(`position-row-${pos.ticker}`)).toBeVisible();
    }
  });
});
