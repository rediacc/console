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
  // Always capture screenshots in CI for debugging and reports
  if (process.env.CI) {
    return 'on';
  }
  if (process.env.SCREENSHOT_ON_FAILURE === 'true') {
    return 'only-on-failure';
  }
  return 'off';
}

function getVideoMode(): 'off' | 'on' | 'retain-on-failure' {
  // Always record video in CI for debugging
  if (process.env.CI) {
    return 'on';
  }
  const value = process.env.RECORD_VIDEO;
  if (value === 'on' || value === 'retain-on-failure') {
    return value;
  }
  return 'off';
}

export default test.defineConfig({
  testDir: './tests',

  /* Global teardown to clean up state file */
  globalTeardown: path.resolve(__dirname, './src/setup/global-teardown.ts'),

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
  reporter: [
    ['html', { outputFolder: 'reports/e2e' }],
    ['json', { outputFile: 'reports/e2e/results.json' }],
  ],

  /* Shared settings for all the projects below */
  use: {
    /* Base URL - Vite dev server with /console/ base path */
    baseURL: process.env.E2E_BASE_URL ?? E2E_DEFAULTS.CONSOLE_URL,

    /* Collect trace for debugging - always in CI, on retry locally */
    trace: process.env.CI ? 'on' : 'on-first-retry',

    /* Screenshot settings - always capture in CI */
    screenshot: getScreenshotMode(),

    /* Video settings - always record in CI */
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

  /* Configure projects for browsers and devices */
  projects: [
    // =========================================================================
    // SETUP PROJECT - Registers user before all tests
    // =========================================================================
    {
      name: 'setup',
      testMatch: /global\.setup\.ts/,
      use: { ...test.devices['Desktop Chrome'] },
      // Setup needs more time: wait for Vite + registration flow
      timeout: 60000,
    },

    // =========================================================================
    // DESKTOP BROWSERS
    // Each test authenticates via login page (no shared auth state needed)
    // =========================================================================
    {
      name: 'chromium',
      use: { ...test.devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
    {
      name: 'firefox',
      use: { ...test.devices['Desktop Firefox'] },
      dependencies: ['setup'],
    },
    {
      name: 'webkit',
      use: { ...test.devices['Desktop Safari'] },
      dependencies: ['setup'],
    },
    {
      name: 'msedge',
      use: { ...test.devices['Desktop Edge'], channel: 'msedge' },
      dependencies: ['setup'],
    },

    // =========================================================================
    // MOBILE DEVICES - Android (Chromium-based)
    // =========================================================================
    {
      name: 'galaxy-s24',
      use: { ...test.devices['Galaxy S24'] },
      dependencies: ['setup'],
    },
    {
      name: 'galaxy-tab-s9',
      use: { ...test.devices['Galaxy Tab S9 landscape'] },
      dependencies: ['setup'],
    },

    // =========================================================================
    // MOBILE DEVICES - iOS (WebKit-based)
    // =========================================================================
    {
      name: 'iphone-15-pro-max',
      use: { ...test.devices['iPhone 15 Pro Max'] },
      dependencies: ['setup'],
    },
    {
      name: 'ipad-pro-11',
      use: { ...test.devices['iPad Pro 11'] },
      dependencies: ['setup'],
    },
  ],

  /* Web server configuration - starts Vite dev server automatically */
  webServer: {
    command: 'npm run --prefix ../.. dev -w @rediacc/web',
    url: 'http://localhost:3000/console/',
    reuseExistingServer: !process.env.CI,
    timeout: 120000, // 2 minutes for Vite to start
    // Capture output for debugging in CI
    stdout: 'pipe',
    stderr: 'pipe',
    // Pass VITE_API_URL to Vite only if explicitly set (for CI tunnel)
    // Otherwise Vite uses default: http://localhost:7322
    env: {
      ...(process.env.VITE_API_URL && { VITE_API_URL: process.env.VITE_API_URL }),
    },
  },
});
