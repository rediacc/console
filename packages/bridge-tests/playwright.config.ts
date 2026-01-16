import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * Playwright configuration for bridge/renet tests.
 * These tests don't require a browser - they test CLI and SSH operations.
 *
 * Infrastructure is auto-provisioned via globalSetup if not already running.
 * Test outputs are saved to reports/ folder (gitignored).
 *
 * CI Mode:
 * - Extracts renet binary from Docker image (RENET_DOCKER_IMAGE)
 * - Uses pre-extracted binary path (RENET_BINARY_PATH)
 * - Longer timeouts and more retries for stability
 */
export default test.defineConfig({
  testDir: './tests',
  /* Global setup ensures infrastructure is running */
  globalSetup: require.resolve('./src/base/bridge-global-setup'),
  globalTeardown: require.resolve('./src/base/bridge-global-teardown'),
  /* Run tests in files sequentially to preserve ordering in reports */
  fullyParallel: false,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* More retries in CI for stability */
  retries: process.env.CI ? 2 : 1,
  /* Single worker for bridge tests to avoid conflicts */
  workers: 1,
  /* Longer timeout in CI (10 min vs 5 min locally) */
  timeout: process.env.CI ? 600000 : 300000,
  /* Reporters: HTML report + text file output for each test */
  reporter: [
    ['html', { outputFolder: 'reports/bridge' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/bridge-logs' }],
  ],
  /* No browser needed for bridge tests */
  use: {
    /* No baseURL needed */
  },
  /* Projects for numeric execution order (01 → 02 → ... → 22)
   * Order maintained by: workers:1 + fullyParallel:false + alphanumeric file naming
   * No dependencies = tests continue even when some fail
   *
   * Note: test-20 (image-build) is disabled on CI - long-running image builds
   * are not suitable for the current CI infrastructure. Run locally with:
   *   npx playwright test --config=playwright.image.config.ts
   */
  projects: [
    { name: 'test-01', testMatch: '01-*.test.ts' },
    { name: 'test-02', testMatch: '02-*.test.ts' },
    { name: 'test-03', testMatch: '03-*.test.ts' },
    { name: 'test-04', testMatch: '04-*.test.ts' },
    { name: 'test-05', testMatch: '05-*.test.ts' },
    { name: 'test-06', testMatch: '06-*.test.ts' },
    { name: 'test-07', testMatch: '07-*.test.ts' },
    { name: 'test-08', testMatch: '08-*.test.ts' },
    { name: 'test-09', testMatch: '09-*.test.ts' },
    { name: 'test-10', testMatch: '10-*.test.ts' },
    { name: 'test-11', testMatch: '11-*.test.ts' },
    { name: 'test-12', testMatch: '12-*.test.ts' },
    { name: 'test-13', testMatch: '13-*.test.ts' },
    { name: 'test-14', testMatch: '14-*.test.ts' },
    { name: 'test-15', testMatch: '15-*.test.ts' },
    { name: 'test-16', testMatch: '16-*.test.ts' },
    { name: 'test-17', testMatch: '17-*.test.ts' },
    { name: 'test-18', testMatch: '18-*.test.ts' },
    { name: 'test-19', testMatch: '19-*.test.ts' },
    // test-20 (image-build) disabled on CI - use playwright.image.config.ts locally
    ...(process.env.CI ? [] : [{ name: 'test-20', testMatch: '20-*.test.ts' }]),
    { name: 'test-21', testMatch: '21-*.test.ts' },
    { name: 'test-22', testMatch: '22-*.test.ts' },
  ],
});
