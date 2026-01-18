import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env') });

// Note: These constants are inlined here because playwright.config.ts is loaded
// by knip before build, and @rediacc/shared/config requires compiled output.
// E2E_PORT is set by run-e2e.sh to avoid port conflicts when running multiple worktrees
const E2E_PORT = Number(process.env.E2E_PORT) || 3000;

const E2E_DEFAULTS = {
  PORT: E2E_PORT,
  CONSOLE_URL: `http://localhost:${E2E_PORT}/console/`,
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
 * - E2E_PORT: Port for Vite dev server (default: 3000, auto-detected by run-e2e.sh)
 * - E2E_BASE_URL: Base URL for the application (default: http://localhost:E2E_PORT/console/)
 * - VITE_API_URL: API backend URL for Vite proxy (e.g., tunnel URL in CI)
 * - API_TIMEOUT: Action timeout in ms (default: 10000)
 * - PAGE_TIMEOUT: Navigation timeout in ms (default: 30000)
 * - STOP_ON_FAILURE: Stop on first failure (default: false)
 * - VM_DEPLOYMENT: Enable VM-dependent tests (default: false)
 * - PWSLOWMO: Slow down browser actions by N milliseconds (for debugging)
 *
 * @see https://playwright.dev/docs/test-configuration
 */

export default test.defineConfig({
  testDir: './tests',

  /* Global teardown to clean up state file */
  globalTeardown: path.resolve(__dirname, './src/setup/global-teardown.ts'),

  /* Run tests sequentially to prevent race conditions and timing issues */
  fullyParallel: false,

  /* Fail the build if you accidentally left test.only in the source code. */
  forbidOnly: true,

  /* No retries - tests should pass consistently */
  retries: 0,

  /* Single worker for maximum stability and resource isolation */
  workers: 1,

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

    /* Collect trace for debugging */
    trace: 'on',

    /* Always capture screenshots */
    screenshot: 'on',

    /* Always record video */
    video: 'on',

    /* Timeout settings with sensible defaults */
    actionTimeout: Number.parseInt(
      process.env.API_TIMEOUT ?? String(E2E_DEFAULTS.KEEPALIVE_TIMEOUT),
      10
    ),
    navigationTimeout: Number.parseInt(
      process.env.PAGE_TIMEOUT ?? String(E2E_DEFAULTS.CONNECTION_TIMEOUT),
      10
    ),

    /* Slow down actions for debugging (set via PWSLOWMO env var) */
    launchOptions: {
      slowMo: process.env.PWSLOWMO ? Number.parseInt(process.env.PWSLOWMO, 10) : undefined,
    },
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
      // Setup needs more time: wait for Vite + registration flow + slower Windows runners
      // Increased to 180s to accommodate Windows tunnel latency (60s health + 60s registration + 30s buffer)
      timeout: 180000,
    },

    // =========================================================================
    // DESKTOP BROWSERS
    // Each test authenticates via login page (no shared auth state needed)
    // Electron tests are excluded - they only run in Electron projects
    // =========================================================================
    {
      name: 'chromium',
      use: { ...test.devices['Desktop Chrome'] },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },
    {
      name: 'firefox',
      use: { ...test.devices['Desktop Firefox'] },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },
    {
      name: 'webkit',
      use: { ...test.devices['Desktop Safari'] },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },
    {
      name: 'msedge',
      use: { ...test.devices['Desktop Edge'], channel: 'msedge' },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },

    // =========================================================================
    // DESKTOP RESOLUTIONS - Common screen sizes for responsive testing
    // Uses Chromium with custom viewports to test layout at different sizes
    // =========================================================================
    {
      name: 'resolution-1920x1080',
      use: {
        ...test.devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 },
      },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },
    {
      name: 'resolution-1366x768',
      use: {
        ...test.devices['Desktop Chrome'],
        viewport: { width: 1366, height: 768 },
      },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },
    {
      name: 'resolution-1536x864',
      use: {
        ...test.devices['Desktop Chrome'],
        viewport: { width: 1536, height: 864 },
      },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },

    // =========================================================================
    // MOBILE DEVICES - Android (Chromium-based)
    // Electron tests are excluded - they only run in Electron projects
    // =========================================================================
    {
      name: 'galaxy-s24',
      use: { ...test.devices['Galaxy S24'] },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },
    {
      name: 'galaxy-tab-s9',
      use: { ...test.devices['Galaxy Tab S9 landscape'] },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },

    // =========================================================================
    // MOBILE DEVICES - iOS (WebKit-based)
    // Electron tests are excluded - they only run in Electron projects
    // =========================================================================
    {
      name: 'iphone-15-pro-max',
      use: { ...test.devices['iPhone 15 Pro Max'] },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },
    {
      name: 'ipad-pro-11',
      use: { ...test.devices['iPad Pro 11'] },
      testIgnore: /tests\/electron\//,
      dependencies: ['setup'],
    },

    // =========================================================================
    // ELECTRON DESKTOP APP - 6 Platform Matrix
    // Tests run against built Electron app (packages/desktop/out/main/index.js)
    // Electron uses HashRouter, so baseURL is empty (paths are hash fragments)
    // Setup project registers user via Chromium, credentials shared via .e2e-state.json
    // =========================================================================
    {
      name: 'electron-linux-x64',
      testMatch: /tests\/electron\/.*\.test\.ts/,
      use: { baseURL: '' },
      dependencies: ['setup'],
    },
    {
      name: 'electron-linux-arm64',
      testMatch: /tests\/electron\/.*\.test\.ts/,
      use: { baseURL: '' },
      dependencies: ['setup'],
    },
    {
      name: 'electron-macos-x64',
      testMatch: /tests\/electron\/.*\.test\.ts/,
      use: { baseURL: '' },
      dependencies: ['setup'],
    },
    {
      name: 'electron-macos-arm64',
      testMatch: /tests\/electron\/.*\.test\.ts/,
      use: { baseURL: '' },
      dependencies: ['setup'],
    },
    {
      name: 'electron-windows-x64',
      testMatch: /tests\/electron\/.*\.test\.ts/,
      use: { baseURL: '' },
      dependencies: ['setup'],
    },
    {
      name: 'electron-windows-arm64',
      testMatch: /tests\/electron\/.*\.test\.ts/,
      use: { baseURL: '' },
      dependencies: ['setup'],
    },
  ],

  /* Web server configuration - starts Vite dev server automatically */
  webServer: {
    command: `npm run --prefix ../.. dev -w @rediacc/web -- --port ${E2E_PORT}`,
    url: E2E_DEFAULTS.CONSOLE_URL,
    reuseExistingServer: false,
    timeout: 120000, // 2 minutes for Vite to start
    stdout: 'pipe',
    stderr: 'pipe',
    // Pass VITE_API_URL to Vite only if explicitly set (for CI tunnel)
    // Otherwise Vite uses default: http://localhost:7322
    env: {
      ...(process.env.VITE_API_URL && { VITE_API_URL: process.env.VITE_API_URL }),
    },
  },
});
