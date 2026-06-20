import { defineConfig, devices } from 'playwright/test';

const port = Number(process.env.PLAYWRIGHT_PORT || 5177);
const baseURL = process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: [
      `PORT=${port}`,
      'APP_ENV=development',
      'BETA_UNLOCK_ALL_FEATURES=true',
      'SESSION_SECRET=playwright-session-secret-000000000000000000',
      'OPENAI_API_KEY=playwright-placeholder-key',
      'CREDANTA_FORCE_LOCAL_STORAGE=true',
      'CREDANTA_DISABLE_RATE_LIMITS=true',
      'CREDANTA_DB_PATH=/tmp/credanta-playwright/app.db',
      'CREDANTA_UPLOAD_DIR=/tmp/credanta-playwright/uploads',
      '.venv/bin/python run.py',
    ].join(' '),
    url: `${baseURL}/healthz`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  outputDir: 'test-results/playwright',
});
