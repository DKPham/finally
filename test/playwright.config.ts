import { defineConfig, devices } from '@playwright/test';

/**
 * FinAlly E2E suite.
 *
 * The app is single-user with one shared SQLite database, so specs run
 * serially (one worker) in file-name order. 01-fresh-start must run against
 * a freshly created database; later specs make relative assertions so they
 * tolerate state left by earlier ones.
 *
 * BASE_URL defaults to http://localhost:8000 (local run); docker compose sets
 * it to http://finally:8000.
 */
const baseURL = process.env.BASE_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 1600, height: 1000 },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1600, height: 1000 } } }],
});
