import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env') });

// Note: These constants are inlined here because playwright.config.ts is loaded
// by knip before build, and @rediacc/shared/config requires compiled output.
const E2E_DEFAULTS = {
  CONSOLE_URL: 'http://localhost:3000/console/',
  KEEPALIVE_TIMEOUT: 10000,
  CONNECTION_TIMEOUT: 30000,
} as const;

/**
 * E2E Test Configuration for Console Web Application
 *
 * This config starts a Vite dev server to test the current source code,
 * NOT the pre-built Docker container assets.
 *
 * Environment Variables:
 * - E2E_BASE_URL: Base URL for the application (default: http://localhost:3000/console/)
 * - VITE_API_URL: API backend URL for Vite proxy (e.g., tunnel URL in CI)
 * - API_TIMEOUT: Action timeout in ms (default: 10000)
 * - PAGE_TIMEOUT: Navigation timeout in ms (default: 30000)
 * - SCREENSHOT_ON_FAILURE: Enable screenshots on failure (default: true in CI)
 * - RECORD_VIDEO: Video recording mode (off, on, retain-on-failure)
 * - STOP_ON_FAILURE: Stop on first failure (default: false)
 * - VM_DEPLOYMENT: Enable VM-dependent tests (default: false)
 *
 * @see https://playwright.dev/docs/test-configuration
 */

function getScreenshotMode(): 'off' | 'on' | 'only-on-failure' {
  if (process.env.CI) {
    return 'only-on-failure';
  }
  if (process.env.SCREENSHOT_ON_FAILURE === 'true') {
    return 'only-on-failure';
  }
  return 'off';
}

function getVideoMode(): 'off' | 'on' | 'retain-on-failure' {
  const value = process.env.RECORD_VIDEO;
  if (value === 'on' || value === 'retain-on-failure') {
    return value;
  }
  return 'off';
}

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
    /* Base URL - Vite dev server with /console/ base path */
    baseURL: process.env.E2E_BASE_URL ?? E2E_DEFAULTS.CONSOLE_URL,

    /* Collect trace when retrying the failed test */
    trace: 'on-first-retry',

    /* Screenshot settings - enabled on failure in CI */
    screenshot: getScreenshotMode(),

    /* Video settings */
    video: getVideoMode(),

    /* Timeout settings with sensible defaults */
    actionTimeout: Number.parseInt(
      process.env.API_TIMEOUT ?? String(E2E_DEFAULTS.KEEPALIVE_TIMEOUT),
      10
    ),
    navigationTimeout: Number.parseInt(
      process.env.PAGE_TIMEOUT ?? String(E2E_DEFAULTS.CONNECTION_TIMEOUT),
      10
    ),
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

  /* Web server configuration - starts Vite dev server automatically */
  webServer: {
    command: 'npm run --prefix ../.. dev -w @rediacc/web',
    url: 'http://localhost:3000/console/',
    reuseExistingServer: !process.env.CI,
    timeout: 120000, // 2 minutes for Vite to start
    // Pass VITE_API_URL to Vite only if explicitly set (for CI tunnel)
    // Otherwise Vite uses default: http://localhost:7322
    env: {
      ...(process.env.VITE_API_URL && { VITE_API_URL: process.env.VITE_API_URL }),
    },
  },
});
