import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env'), quiet: true });

/**
 * Playwright configuration for the k8s repo topology (suite 15, `E2E K8s` job).
 *
 * Drives a single-node k3s cluster living inside a datastore-backed repo image
 * on a worker VM: install, deploy with the router annotation contract, PV-per-
 * CoW-image provisioning, the flagship namespace fork (instant CoW, data
 * divergence, parent unchanged), and — when a second worker is present — a
 * cross-cluster migrate with measured downtime.
 *
 * Requires K8S_MODE=1 and at least one worker VM (the test-bridge-k8s CI job /
 * a local `ops up` with VM_WORKERS set).
 *
 * Run with: npx playwright test --config=playwright.k8s.config.ts
 */
export default test.defineConfig({
  testDir: './tests/kube',
  globalSetup: require.resolve('./src/base/bridge-global-setup'),
  globalTeardown: require.resolve('./src/base/bridge-global-teardown'),
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  /* Deterministic failures must not re-run the serial chain (campaign fail-fast). */
  retries: 0,
  /* Stop at the first failure: one test, not a skip-cascade. */
  maxFailures: 1,
  workers: 1,
  timeout: 600000,
  reporter: [
    ['html', { outputFolder: 'reports/bridge-k8s' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/bridge-k8s-logs' }],
  ],
  use: {
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'k8s-15', testMatch: '15-*.test.ts' }],
});
