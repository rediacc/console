import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env'), quiet: true });

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
  /* Topology-specific suites live in subdirs and each has its own config that
   * scopes to it (ceph -> playwright.ceph.config.ts, kube -> playwright.k8s*.
   * config.ts, migrate -> playwright.migrate.config.ts). The projects below
   * match `NN-*.test.ts` recursively, so without these ignores this base
   * (worker-topology) run COLLECTS the kube/migrate suites and then skips
   * every one of them at runtime for lack of a cluster/second-group — 38
   * dishonest "skipped" lines that look like coverage but run elsewhere. Only
   * ceph was excluded originally; kube/ and migrate/ were added later and the
   * ignore list was never updated. Keep this list in sync with the subdirs. */
  testIgnore: ['**/ceph/**', '**/kube/**', '**/migrate/**', '**/ops-lifecycle/**'],
  /* Global setup ensures infrastructure is running */
  globalSetup: require.resolve('./src/base/bridge-global-setup'),
  globalTeardown: require.resolve('./src/base/bridge-global-teardown'),
  /* Run tests in files sequentially to preserve ordering in reports */
  fullyParallel: false,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* One retry in CI (with --max-failures=3, this is enough to distinguish flaky from broken) */
  retries: process.env.CI ? 1 : 1,
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
   * Deliberately-local suites (test-20 image-build, the FULL_INTEGRATION legs,
   * CLI_SUITE) and the reasons they are not on every CI leg are documented in
   * packages/e2e-tests/README.md ("Deliberately not in CI").
   */
  projects: [
    { name: 'test-01', testMatch: '01-*.test.ts' },
    { name: 'test-02', testMatch: '02-*.test.ts' },
    { name: 'test-03', testMatch: '03-*.test.ts' },
    { name: 'test-04', testMatch: '04-*.test.ts' },
    { name: 'test-05', testMatch: '05-*.test.ts' },
    { name: 'test-06', testMatch: '06-*.test.ts' },
    { name: 'test-07', testMatch: '07-*.test.ts' },
    // test-08 and test-09 (Ceph) moved to tests/ceph/ - use playwright.ceph.config.ts
    { name: 'test-10', testMatch: '10-*.test.ts' },
    { name: 'test-11', testMatch: '11-*.test.ts' },
    // Full-integration composition suites (12a/12b/12d): they re-compose the
    // per-primitive suites 01-11 into longer workflows. Composition logic is
    // distro-agnostic, so on CI they run only on the FULL_INTEGRATION legs
    // (ct-tests.yml matrix include: one apt-family + one rpm-family leg).
    // Locally (no CI) they always run, so they can never go dark on a dev box.
    // 12c is Ceph-only and lives in playwright.ceph.config.ts (ceph-12c).
    ...(process.env.CI && process.env.FULL_INTEGRATION !== '1'
      ? []
      : [{ name: 'test-12', testMatch: ['12a-*.test.ts', '12b-*.test.ts', '12d-*.test.ts'] }]),
    { name: 'test-13', testMatch: '13-*.test.ts' },
    // 13b (live CRIU fork checkpoint, console#440) is genuinely distro-sensitive
    // (CRIU availability + kernel interaction), so it rides the FULL_INTEGRATION
    // legs only. On those legs CRIU_EXPECTED=1 flips its "CRIU absent" guard from
    // a silent skip into a failure (prove-the-instrument).
    ...(process.env.CI && process.env.FULL_INTEGRATION !== '1'
      ? []
      : [{ name: 'test-13b', testMatch: '13b-*.test.ts' }]),
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
    // CLI-migrate routing (suite 23) — first rdc-driven e2e (CliRunner). Two
    // workers, no ceph; distro-agnostic routing logic, so CI runs it on the
    // single CLI_SUITE leg (ct-tests.yml ubuntu-24.04 include). Always runs
    // locally.
    ...(process.env.CI && process.env.CLI_SUITE !== '1'
      ? []
      : [{ name: 'test-23', testMatch: '23-*.test.ts' }]),
    // Chunk-store backup, machine tier (suite 25). Unconditional: it needs
    // only a worker VM, which every E2E Workers leg has, and it carries the
    // live coverage of the `backup_verify` verb (check:ci-e2e-coverage counts a
    // verb dark unless a suite a LIVE config selects exercises it). It never
    // skips where a worker exists, which is what `--fail-on-skip` requires.
    { name: 'test-25', testMatch: '25-*.test.ts' },
    // Suite 26 (control plane + upload engine) needs an account server and a
    // renet that registers the chunk-store run verb — neither exists on the
    // E2E Workers legs, and a skip there is a job failure. Gated, so CI
    // collects nothing rather than skipping. Locally it always runs and fails
    // closed on its own prerequisites.
    ...(process.env.CI && process.env.BACKUP_STORAGE_SUITE !== '1'
      ? []
      : [{ name: 'test-26', testMatch: '26-*.test.ts' }]),
  ],
});
