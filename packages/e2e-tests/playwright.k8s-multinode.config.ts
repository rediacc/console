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
  projects: [
    { name: 'k8s-multinode-17', testMatch: '17-*.test.ts' },
    // Suite 24 (cluster licensing) rides this topology behind an explicit
    // opt-in, mirroring suite 23's CLI_SUITE gate in playwright.config.ts. The
    // ct-tests multinode job now lights it: it starts an in-job TEST_MODE
    // account server and sets CLUSTER_LICENSING_SUITE=1. The gate stays because
    // the suite needs that server plus a subscription token on top of the
    // fleet, and collecting it in a job that supplies neither would either red
    // the job or become the silent skip the suite's own prerequisite gate
    // exists to forbid.
    ...(process.env.CI && process.env.CLUSTER_LICENSING_SUITE !== '1'
      ? []
      : [{ name: 'k8s-multinode-24', testMatch: '24-*.test.ts' }]),
  ],
});
