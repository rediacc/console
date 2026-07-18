import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env'), quiet: true });

/**
 * Playwright configuration for the dual-KVM-group migration topology (suite 18,
 * `Bridge Migrate` job).
 *
 * Drives TWO concurrent KVM groups — the ambient group A (renet11 / 192.168.111)
 * plus a second group B (renet12 / 192.168.112, disjoint VM IDs) — and migrates
 * a running single-node k3s cluster from a group-A worker to a group-B worker
 * across the two private LANs: the local rehearsal of the wave-L cross-DC demo.
 * Group B is driven by its own per-group OpsManager (getOpsManagerForGroup) so
 * its `renet ops` subprocesses never inherit group A's VM_NET/DOCKER_REGISTRY.
 *
 * The .env drives group A (the global setup / source fleet). Group B must
 * already be booted (VM_NET=renet12, VM_BRIDGE=5, VM_WORKERS=51) before this
 * config runs. DUAL_GROUP=1 arms the suite; the global setup is invoked with
 * BRIDGE_TEST_SKIP_RESET=1 locally so it does not tear group A down.
 *
 *   DUAL_GROUP=1 K8S_MODE=1 npx playwright test --config=playwright.migrate.config.ts
 */
process.env.DUAL_GROUP = process.env.DUAL_GROUP ?? '1';

export default test.defineConfig({
  testDir: './tests/migrate',
  globalSetup: require.resolve('./src/base/bridge-global-setup'),
  globalTeardown: require.resolve('./src/base/bridge-global-teardown'),
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  /* Campaign strict profile: deterministic failures do not re-run the chain. */
  retries: 0,
  /* Stop at the first failure: one test, not a skip-cascade. */
  maxFailures: 1,
  workers: 1,
  timeout: 900000,
  reporter: [
    ['html', { outputFolder: 'reports/bridge-migrate' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/bridge-migrate-logs' }],
  ],
  use: {
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'migrate-18', testMatch: '18-*.test.ts' }],
});
