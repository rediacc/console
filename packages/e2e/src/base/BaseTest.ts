import { test as baseTest, expect } from '@playwright/test';
import { TestDataManager } from '../utils/data/TestDataManager';
import { TestReporter } from '../utils/report/TestReporter';
import { ScreenshotManager } from '../utils/screenshot/ScreenshotManager';

export interface TestFixtures {
  screenshotManager: ScreenshotManager;
  testReporter: TestReporter;
  testDataManager: TestDataManager;
}

/* eslint-disable react-hooks/rules-of-hooks -- Playwright fixture pattern uses 'use' function, not a React hook */
export const test = baseTest.extend<TestFixtures>({
  screenshotManager: async ({ page }, use, testInfo) => {
    const manager = new ScreenshotManager(page, testInfo);
    await use(manager);
  },

  testReporter: async ({ page }, use, testInfo) => {
    const reporter = new TestReporter(page, testInfo);
    await use(reporter);
  },

  testDataManager: async ({ browser: _browser }, use, testInfo) => {
    // Pass worker ID for per-worker state isolation in parallel execution
    const workerId = testInfo.workerIndex.toString();
    const dataManager = new TestDataManager(workerId, testInfo.project.name);
    await use(dataManager);
  },
});
/* eslint-enable react-hooks/rules-of-hooks */

export { expect };
