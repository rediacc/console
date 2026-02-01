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
    { name: 'core', testMatch: '01-core/**/*.test.ts' },
    { name: 'resources', testMatch: '02-resources/**/*.test.ts' },
    { name: 'operations', testMatch: '03-operations/**/*.test.ts' },
    { name: 'security', testMatch: '04-security/**/*.test.ts' },
    { name: 'ceph', testMatch: '05-ceph/**/*.test.ts' },
    { name: 'errors', testMatch: '06-errors/**/*.test.ts' },
    { name: 'edition', testMatch: '07-edition/**/*.test.ts' },
    { name: 'e2e', testMatch: '08-e2e/**/*.test.ts' },
    { name: 'vscode', testMatch: '09-vscode/**/*.test.ts' },
    { name: 's3', testMatch: '10-s3/**/*.test.ts' },
  ],
});
