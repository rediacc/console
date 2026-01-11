import { test as baseTest, expect } from '@playwright/test';
import { ScreenshotManager } from '../utils/screenshot/ScreenshotManager';
import { TestReporter } from '../utils/report/TestReporter';
import { TestDataManager } from '../utils/data/TestDataManager';

export interface TestFixtures {
  screenshotManager: ScreenshotManager;
  testReporter: TestReporter;
  testDataManager: TestDataManager;
}

export const test = baseTest.extend<TestFixtures>({

  screenshotManager: async ({ page }, use, testInfo) => {
    const screenshotManager = new ScreenshotManager(page, testInfo);
    await use(screenshotManager);
  },

  testReporter: async ({ page }, use, testInfo) => {
    const testReporter = new TestReporter(page, testInfo);
    await use(testReporter);
  },

  testDataManager: async ({}, use) => {
    const testDataManager = new TestDataManager();
    await use(testDataManager);
  }
});

export { expect };