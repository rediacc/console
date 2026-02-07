import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * Playwright configuration for CLI tests.
 * These tests don't require a browser - they test CLI command execution.
 *
 * Execution model:
 * - Global setup validates API endpoint and creates master test account
 * - Tests run sequentially by category to avoid API conflicts
 * - Each test logs output for TextFileReporter to capture
 */
export default test.defineConfig({
  testDir: './tests',

  /* Global setup/teardown */
  globalSetup: path.resolve(__dirname, './src/base/cli-global-setup.ts'),
  globalTeardown: path.resolve(__dirname, './src/base/cli-global-teardown.ts'),

  /* Run tests in files sequentially to preserve ordering in reports */
  fullyParallel: false,

  /* Fail the build on CI if test.only is left in source */
  forbidOnly: !!process.env.CI,

  /* Retry failed tests locally, but not in CI for faster feedback */
  retries: process.env.CI ? 0 : 1,

  /* Single worker to avoid API conflicts */
  workers: 1,

  /* 2 minute timeout for CLI operations */
  timeout: 120000,

  /* Reporters: HTML + text file output per test */
  reporter: [
    ['html', { outputFolder: 'reports/cli' }],
    ['./src/reporters/TextFileReporter.ts', { outputDir: 'reports/cli-logs' }],
  ],

  /* No browser needed for CLI tests */
  use: {},

  /* Projects for category-based execution */
  projects: [
    // Cloud API tests — run against backend via tunnel
    { name: 'cloud', testMatch: '**/*.cloud.test.ts' },
    // Error handling — subset of cloud tests
    { name: 'errors', testMatch: '**/*.errors.cloud.test.ts' },
    // E2E tests — run on Linux with local VMs (requires renet)
    { name: 'e2e', testMatch: '**/*.e2e.test.ts' },
    // Context management — standalone, no backend needed
    { name: 'context', testMatch: 'context/**/*.test.ts' },
    // VSCode — standalone detection + cloud integration
    { name: 'vscode', testMatch: 'vscode/**/*.test.ts' },
    // S3 — requires RustFS
    { name: 's3', testMatch: 's3/**/*.test.ts' },
    // Edition-specific tests — ENTERPRISE context
    { name: 'edition', testMatch: 'edition/**/*.cloud.test.ts' },
    // Ceph cloud tests only (for ceph-specific CI job)
    { name: 'ceph-cloud', testMatch: 'ceph/**/*.cloud.test.ts' },
    // Ceph E2E tests only (for ceph VM CI job)
    { name: 'ceph-e2e', testMatch: 'ceph/**/*.e2e.test.ts' },
  ],
});
