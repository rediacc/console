import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env'), quiet: true });

/**
 * Suite 27 (backup browse-at) -- its own config, because the base one's
 * globalSetup would destroy the fleet this suite runs against.
 *
 * `playwright.config.ts` wires `bridge-global-setup`, whose step 1 resets every
 * VM (`ops up --force`) and whose step 7 runs
 *
 *     sudo renet datastore init --path /mnt/rediacc --size 10G --force
 *
 * on every worker (OpsManager.initializeAllDatastores). `--force` means
 * `ds.Cleanup()` -- it DELETES every repository image on the machine
 * (datastore_init.go:106-120). That is a reasonable isolation move for a suite
 * that owns the fleet, and it is collateral damage for one that does not: a
 * local fleet is shared with other sessions and suites.
 *
 * Suite 27 needs none of it. It registers its own machine, creates its own
 * repository through `rdc repo create` (the only path that installs a
 * repository license, which the snapshot and browse-at verbs both refuse
 * without), and lays down a datastore only when the worker genuinely has none.
 * What it does need -- a current renet on the worker -- the CLI deploys itself
 * on the first machine connection.
 *
 * Run:
 *   BACKUP_BROWSE_AT_SUITE=1 VM_WORKERS="11" \
 *     REDIACC_ACCOUNT_SERVER=http://<host>:<port> \
 *     E2E_ACCOUNT_API_TOKEN=<token with backup:read> \
 *     E2E_BACKUP_S3_KEY=<store key> E2E_BACKUP_S3_SECRET=<store secret> \
 *     npx playwright test --config playwright.backup-browse-at.config.ts
 */
export default test.defineConfig({
  testDir: './tests',
  // No globalSetup / globalTeardown on purpose. See the header.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 1_800_000,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'reports/backup-browse-at', open: 'never' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/backup-browse-at-logs' }],
  ],
  outputDir: 'test-results/backup-browse-at',
  use: { trace: 'off', screenshot: 'off', video: 'off' },
  projects: [{ name: 'test-27', testMatch: '27-*.test.ts' }],
});
