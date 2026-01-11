import * as test from '@playwright/test';
import dotenv from 'dotenv';
import path from 'path';

dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * E2E Test Configuration for Console Web Application
 *
 * Environment Variables:
 * - E2E_BASE_URL: Base URL for the application (required in CI, defaults to localhost:7322)
 * - API_TIMEOUT: Action timeout in ms (default: 10000)
 * - PAGE_TIMEOUT: Navigation timeout in ms (default: 30000)
 * - SCREENSHOT_ON_FAILURE: Enable screenshots on failure (default: true in CI)
 * - RECORD_VIDEO: Video recording mode (off, on, retain-on-failure)
 * - STOP_ON_FAILURE: Stop on first failure (default: false)
 * - VM_DEPLOYMENT: Enable VM-dependent tests (default: false)
 *
 * @see https://playwright.dev/docs/test-configuration
 */
export default test.defineConfig({
  testDir: './tests',

  /* Run tests in files in parallel */
  fullyParallel: true,

  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,

  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,

  /* Opt out of parallel tests on CI for stability */
  workers: process.env.CI ? 1 : undefined,

  /* Stop test run after first test failure (including all retries) */
  maxFailures: process.env.STOP_ON_FAILURE === 'true' ? 1 : undefined,

  /* Reporter to use */
  reporter: [['html', { outputFolder: 'reports/e2e' }]],

  /* Shared settings for all the projects below */
  use: {
    /* Base URL - uses tunnel URL in CI or localhost for local dev */
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:7322',

    /* Collect trace when retrying the failed test */
    trace: 'on-first-retry',

    /* Screenshot settings - enabled on failure in CI */
    screenshot: process.env.CI ? 'only-on-failure' : (process.env.SCREENSHOT_ON_FAILURE === 'true' ? 'only-on-failure' : 'off'),

    /* Video settings */
    video: (process.env.RECORD_VIDEO as 'off' | 'on' | 'retain-on-failure') || 'off',

    /* Timeout settings with sensible defaults */
    actionTimeout: parseInt(process.env.API_TIMEOUT || '10000'),
    navigationTimeout: parseInt(process.env.PAGE_TIMEOUT || '30000'),
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...test.devices['Desktop Chrome'] },
    },

    // Firefox and WebKit disabled - not installed in CI environment
    // Uncomment to enable multi-browser testing locally
    // {
    //   name: 'firefox',
    //   use: { ...test.devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   use: { ...test.devices['Desktop Safari'] },
    // },
  ],
});
