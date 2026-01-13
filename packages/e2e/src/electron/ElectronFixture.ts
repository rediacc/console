import path from 'node:path';
import { test as base, _electron as electron, type ElectronApplication } from '@playwright/test';
import { NETWORK_DEFAULTS } from '../utils/constants';

/**
 * Electron-specific fixtures for E2E testing.
 *
 * These fixtures launch the Electron desktop app and provide access to both
 * the ElectronApplication instance (for main process interaction) and the
 * Page instance (for renderer/UI testing).
 *
 * Usage:
 * ```typescript
 * import { electronTest, expect } from './ElectronFixture';
 *
 * electronTest('my test', async ({ page, electronApp }) => {
 *   // page works like normal Playwright page
 *   await page.click('button');
 *
 *   // electronApp provides main process access
 *   const appName = await electronApp.evaluate(({ app }) => app.getName());
 * });
 * ```
 */

export interface ElectronFixtures {
  /** The Electron application instance for main process interaction */
  electronApp: ElectronApplication;
}

/**
 * Launch the Electron application for testing.
 * Uses the built Electron main process from packages/desktop/out/main/index.js.
 * Run `npm run build -w @rediacc/desktop` to build first.
 * @returns Promise resolving to the ElectronApplication instance
 */
async function launchElectronApp(): Promise<ElectronApplication> {
  // Path to the built Electron main process
  // __dirname is packages/e2e/src/electron/, go up 3 levels to packages/
  const mainPath = path.resolve(__dirname, '../../../desktop/out/main/index.js');

  return electron.launch({
    args: [mainPath],
    // Set cwd to desktop package for proper native module resolution
    cwd: path.resolve(__dirname, '../../../desktop'),
    env: {
      ...process.env,
      // Pass API URL to the app (used by Vite/React for API calls)
      VITE_API_URL: process.env.VITE_API_URL ?? NETWORK_DEFAULTS.API_URL,
      // Disable auto-updater during tests to avoid update prompts
      ELECTRON_DISABLE_AUTO_UPDATER: 'true',
      // Set NODE_ENV to test for conditional test behavior
      NODE_ENV: 'test',
    },
    // Increase timeout for slower CI environments
    timeout: 60000,
  });
}

/**
 * Extended Playwright test with Electron-specific fixtures.
 *
 * This test fixture:
 * 1. Launches the built Electron app from packages/desktop/out/main/index.js
 * 2. Waits for the first window to appear
 * 3. Provides both `page` and `electronApp` to tests
 * 4. Automatically closes the app after each test
 */
export const electronTest = base.extend<ElectronFixtures>({
  // Use browserName dependency to satisfy ESLint no-empty-pattern rule
  electronApp: async ({ browserName: _browserName }, callback) => {
    const app = await launchElectronApp();
    await callback(app);
    await app.close();
  },

  // Override the default page fixture to use Electron's window
  page: async ({ electronApp }, callback) => {
    // Wait for a window that is NOT DevTools
    // The app window loads file:// or has the actual app content
    const page = await electronApp.waitForEvent('window', {
      predicate: (p) => {
        const url = p.url();
        // DevTools URLs contain 'devtools://'
        // App window loads from file:// protocol
        return !url.includes('devtools://');
      },
      timeout: 30000,
    });

    // Wait for the app to be ready
    await page.waitForLoadState('domcontentloaded');
    // Wait for React to hydrate - #root should have children after hydration
    await page.waitForSelector('#root', { timeout: 10000 });
    // Wait for network to settle after initial render
    await page.waitForLoadState('networkidle');
    await callback(page);
  },
});

export { expect } from '@playwright/test';

/**
 * Helper to check if a test is running in an Electron project.
 * Use this in tests that should behave differently for Electron vs web.
 *
 * @param projectName - The project name from testInfo.project.name
 * @returns true if running in an Electron project
 */
export function isElectronProject(projectName: string): boolean {
  return projectName.startsWith('electron-');
}
