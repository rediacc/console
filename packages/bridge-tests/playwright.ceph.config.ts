import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * Playwright configuration for Ceph-specific bridge/renet tests.
 * These tests require a Ceph cluster (VM_CEPH_NODES must be set).
 *
 * Test files in tests/ceph/:
 * - 08-ceph-pool-image.test.ts: Pool and image operations
 * - 09-ceph-snapshot-clone.test.ts: Snapshot and clone operations (COW)
 * - 12c-full-integration-ceph.test.ts: Full Ceph workflow integration
 *
 * Run with: npm run test:bridge:ceph
 * Or: npx playwright test --config=playwright.ceph.config.ts
 */
export default test.defineConfig({
  testDir: './tests/ceph',
  /* Global setup ensures infrastructure is running */
  globalSetup: require.resolve('./src/base/bridge-global-setup'),
  globalTeardown: require.resolve('./src/base/bridge-global-teardown'),
  /* Run tests in files sequentially to preserve ordering in reports */
  fullyParallel: false,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* More retries for stability */
  retries: 2,
  /* Single worker for bridge tests to avoid conflicts */
  workers: 1,
  /* 10 minute timeout - consistent for CI and local */
  timeout: 600000,
  /* Reporters: HTML report + text file output for each test */
  reporter: [
    ['html', { outputFolder: 'reports/bridge-ceph' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/bridge-ceph-logs' }],
  ],
  /* Trace on failure for debugging */
  use: {
    trace: 'retain-on-failure',
  },
  /* Projects for Ceph tests */
  projects: [
    { name: 'ceph-08', testMatch: '08-*.test.ts' },
    { name: 'ceph-09', testMatch: '09-*.test.ts' },
    { name: 'ceph-12c', testMatch: '12c-*.test.ts' },
  ],
});
