import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env'), quiet: true });

/**
 * Playwright configuration for the multi-node k8s cluster topology (suite 17,
 * `Bridge K8s Multinode` job).
 *
 * Drives a 2-node k3s cluster (server on worker 1, agent on worker 2, both bound
 * to their real private NICs — the wave-7 join fix), a Ceph-backed PV consumed by
 * an agent pod, then the whole-cluster fork and migrate flows (S2 verdicts):
 * coordinated CoW of the control-plane + agent images with per-node identity
 * rewrite (server first, then agents), drain-before-reflink, and a measured
 * migrate downtime. Parent divergence is proven CoW-isolated; teardown leaves no
 * orphan repos/RADOS namespaces.
 *
 * Requires K8S_MODE=1, a Ceph topology (VM_CEPH_NODES), and TWO worker VMs
 * (VM_WORKERS='11 12'). Run with:
 *   npx playwright test --config=playwright.k8s-multinode.config.ts
 */
export default test.defineConfig({
  testDir: './tests/kube',
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
    ['html', { outputFolder: 'reports/bridge-k8s-multinode' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/bridge-k8s-multinode-logs' }],
  ],
  use: {
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'k8s-multinode-17', testMatch: '17-*.test.ts' }],
});
