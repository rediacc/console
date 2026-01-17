import path from 'node:path';
import * as test from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * Playwright configuration for image build tests.
 *
 * These tests run locally on the host machine, not on VMs.
 * No browser or infrastructure setup required.
 *
 * Usage:
 *   npx playwright test --config=playwright.image.config.ts
 */
export default test.defineConfig({
  testDir: './tests',
  /* NO global setup - image tests run locally */
  /* Run tests sequentially since image builds are resource-intensive */
  fullyParallel: false,
  /* Fail the build on CI if you accidentally left test.only in the source code */
  forbidOnly: !!process.env.CI,
  /* No retries for long-running image builds */
  retries: 0,
  /* Single worker to avoid concurrent builds */
  workers: 1,
  /* Long timeout for image builds (35 minutes per test) */
  timeout: 35 * 60 * 1000,
  /* Reporters */
  reporter: [['html', { outputFolder: 'reports/image' }], ['list']],
  /* Only run tests matching the image pattern */
  testMatch: '**/20-image-build.test.ts',
  /* No browser needed */
  use: {},
  /* Single project */
  projects: [
    {
      name: 'image',
      testMatch: '**/20-image-build.test.ts',
    },
  ],
});
