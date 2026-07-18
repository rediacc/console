import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env'), quiet: true });

/**
 * Playwright configuration for the combined workers + Ceph topology.
 *
 * Unlike playwright.ceph.config.ts (Ceph nodes only, no workers), this config
 * drives the product paths that need BOTH a Ceph cluster and worker/client
 * machines: a repo-hosting worker consuming a Ceph RBD datastore, and
 * multi-client read-only RBD consumption with per-client COW overlays.
 *
 * Requires VM_CEPH_NODES and VM_WORKERS to both be set (the
 * test-bridge-ceph-workers CI job / a local combined `ops up`).
 *
 * Test files in tests/ceph/:
 * - 13-ceph-datastore.test.ts:   RBD-backed datastore init/fork/unfork lifecycle
 * - 14-ceph-multiclient.test.ts: multi-client read-only clone + per-client COW
 *
 * Run with: npx playwright test --config=playwright.ceph-workers.config.ts
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
  /* Campaign fail-fast: no retry of a deterministic failure. */
  retries: 0,
  /* Stop at the first failure: one test, not a skip-cascade. */
  maxFailures: 1,
  /* Single worker for bridge tests to avoid conflicts */
  workers: 1,
  /* 10 minute timeout - consistent for CI and local */
  timeout: 600000,
  /* Reporters: HTML report + text file output for each test */
  reporter: [
    ['html', { outputFolder: 'reports/bridge-ceph-workers' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/bridge-ceph-workers-logs' }],
  ],
  /* Trace on failure for debugging */
  use: {
    trace: 'retain-on-failure',
  },
  /* Projects for the combined workers + Ceph suites */
  projects: [
    { name: 'ceph-13', testMatch: '13-*.test.ts' },
    { name: 'ceph-14', testMatch: '14-*.test.ts' },
  ],
});
