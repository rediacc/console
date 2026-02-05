import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { test as baseTest, expect } from '@playwright/test';
import { TestDataManager } from '../utils/data/TestDataManager';
import { INTERACTION_HIGHLIGHT_SCRIPT } from '../utils/interaction-highlight';
import { TestReporter } from '../utils/report/TestReporter';
import { ScreenshotManager } from '../utils/screenshot/ScreenshotManager';

interface TestFixtures {
  screenshotManager: ScreenshotManager;
  testReporter: TestReporter;
  testDataManager: TestDataManager;
  _blockExternalTracking: undefined;
  _interactionHighlight: undefined;
  _videoSaver: undefined;
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

  // Block external analytics/tracking domains that may be unreachable in CI or
  // Codespaces, preventing them from blocking the page 'load' event.
  _blockExternalTracking: [
    async ({ page }, use) => {
      await page.route(
        (url) => url.hostname === 'plausible.rediacc.com',
        (route) => route.abort()
      );
      await use(undefined);
    },
    { auto: true },
  ],

  // Inject interaction highlight overlays (clicks, focus, keystrokes) into the page
  // so they appear in recorded videos.
  _interactionHighlight: [
    async ({ page }, use) => {
      await page.context().addInitScript(INTERACTION_HIGHLIGHT_SCRIPT);
      await use(undefined);
    },
    { auto: true },
  ],

  // Auto-save video with deterministic filename after each test.
  // Derives filename from test file path: 01-01-registration.test.ts → 01-01-registration.webm
  // Videos are saved to packages/e2e/videos/user-guide/ for CI artifact upload.
  _videoSaver: [
    async ({ page }, use, testInfo) => {
      await use(undefined);

      const video = page.video();
      if (!video) return;

      // Close the page to finalize the video recording. video.saveAs() waits
      // for the browser context to close, but fixture teardown runs BEFORE the
      // page fixture closes it — causing a deadlock. Closing explicitly here
      // lets saveAs() proceed immediately. page.close() is idempotent so the
      // page fixture's subsequent close is a no-op.
      await page.close();

      const testBasename = path.basename(testInfo.file, '.test.ts');
      const videosDir = path.resolve(__dirname, '../../videos/user-guide');
      await mkdir(videosDir, { recursive: true });

      const destPath = path.join(videosDir, `${testBasename}.webm`);
      try {
        await video.saveAs(destPath);
      } catch {
        // Video may not be available if browser crashed or test was skipped
      }
    },
    { auto: true },
  ],
});
/* eslint-enable react-hooks/rules-of-hooks */

export { expect };
