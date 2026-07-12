import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env'), quiet: true });

// The k3s lifecycle primitives this suite drives legitimately run for MINUTES:
// `kube identity-rewrite` performs the full F1-F8 control-plane PKI re-mint (~120s),
// and `repository down` must wait out every pod's termination grace period before it
// can release the volumes. The generic 120s bridge bound TRUNCATES them: the re-mint
// was completing at 117-120s (passing on a coin flip) and was then SIGKILLed at
// exactly 120.0s. Raise the floor in the suite's own config so CI does not depend on
// a local .env value.
if (Number(process.env.BRIDGE_TIMEOUT ?? 0) < 360_000) {
  process.env.BRIDGE_TIMEOUT = '360000';
}

/**
 * Playwright configuration for the Ceph-backed k8s repo topology (suite 16,
 * `Bridge K8s Ceph` job — the flagship).
 *
 * Drives a single-node k3s cluster on a worker VM running ceph-csi (RBD) against
 * the Ceph cluster on the ceph nodes: deploy a StatefulSet whose PVC binds to a
 * dynamically provisioned RBD image scoped into the repo's RADOS namespace, fork
 * the repo into a NEW RADOS namespace (CoW RBD clones, RW divergence, parent
 * untouched), and tear down with no orphan images/namespaces.
 *
 * Requires K8S_MODE=1, a Ceph topology (VM_CEPH_NODES), and at least one worker
 * VM (the test-bridge-k8s-ceph CI job / a local `ops up` with VM_WORKERS +
 * VM_CEPH_NODES set).
 *
 * Run with: npx playwright test --config=playwright.k8s-ceph.config.ts
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
  timeout: 900000,
  reporter: [
    ['html', { outputFolder: 'reports/bridge-k8s-ceph' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/bridge-k8s-ceph-logs' }],
  ],
  use: {
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'k8s-ceph-16', testMatch: '16-*.test.ts' }],
});
