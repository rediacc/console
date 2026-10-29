import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env'), quiet: true });

/**
 * Suite 31 (backup large-repo, box K10 of agent/plans/PLAN-backup-program.md) -- its own config, for the reason suite 27's has: the base config's globalSetup resets the fleet and runs `renet datastore init --force` on every worker, which deletes every repository image on the machine.
 *
 * Suite 31 lays down its own 80G datastore and a 60G repository, seeds 50 GiB, snapshots, changes 256 MiB and snapshots again, so it runs only on a worker VM with a 100 GB disk. Only the standalone nightly `ct-backup-perf.yml` provides one; the 120 minute job ceiling is why this config's timeout is 100 minutes.
 *
 * Run (the workflow's recipe, on a host with the disk):
 *   BACKUP_LARGE_REPO_SUITE=1 VM_WORKERS="11" VM_DSK=100 \
 *     REDIACC_ACCOUNT_SERVER=http://<host>:<port> \
 *     E2E_ACCOUNT_API_TOKEN=<token with backup:read> \
 *     E2E_BACKUP_S3_KEY=<store key> E2E_BACKUP_S3_SECRET=<store secret> \
 *     npx playwright test --config playwright.backup-large-repo.config.ts
 */
export default test.defineConfig({
  testDir: './tests',
  // No globalSetup / globalTeardown on purpose. See the header.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 6_000_000,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'reports/backup-large-repo', open: 'never' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/backup-large-repo-logs' }],
  ],
  outputDir: 'test-results/backup-large-repo',
  use: { trace: 'off', screenshot: 'off', video: 'off' },
  projects: [{ name: 'test-31', testMatch: '31-*.test.ts' }],
});
