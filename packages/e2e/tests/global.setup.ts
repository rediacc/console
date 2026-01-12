import { test as setup } from '@playwright/test';
import { TEST_CREDENTIALS } from '@rediacc/shared';
import { LoginPage } from '../pages/auth/LoginPage';

/**
 * Global Setup - Per-Browser User Registration
 *
 * This setup project runs before each browser's tests to:
 * 1. Register a unique user account for this browser
 * 2. Save the authentication state to a browser-specific file
 *
 * This prevents session conflicts when running multiple browsers in parallel,
 * as the middleware invalidates sessions when the same user logs in from
 * a different device.
 *
 * Each browser gets its own unique user:
 * - chromium: e2e-chromium-{timestamp}@rediacc.local
 * - firefox: e2e-firefox-{timestamp}@rediacc.local
 * - webkit: e2e-webkit-{timestamp}@rediacc.local
 * - msedge: e2e-msedge-{timestamp}@rediacc.local
 *
 * Device projects (galaxy-s24, iphone-15-pro-max, etc.) reuse the auth state
 * from their underlying browser engine (chromium or webkit).
 */

const AUTH_DIR = 'playwright/.auth';

setup('authenticate', async ({ page }, testInfo) => {
  const loginPage = new LoginPage(page);

  // Extract browser name from project (e.g., 'chromium-setup' -> 'chromium')
  const browser = testInfo.project.name.replace('-setup', '');
  const timestamp = Date.now();
  const email = `e2e-${browser}-${timestamp}@${TEST_CREDENTIALS.TEST_EMAIL_DOMAIN}`;
  const organizationName = `E2E ${browser} ${timestamp}`;

  console.warn(`[Setup] Registering user for ${browser}: ${email}`);

  // Navigate to login page
  await loginPage.navigate();

  // Go to registration form
  await loginPage.clickRegister();

  // Wait for registration form to be visible
  await page.waitForTimeout(1000);

  // Fill registration form with unique user
  await loginPage.fillRegistrationForm(
    organizationName,
    email,
    TEST_CREDENTIALS.TEST_PASSWORD,
    TEST_CREDENTIALS.TEST_PASSWORD,
    true
  );

  // Submit registration
  await loginPage.submitRegistrationForm();

  // Wait for verification step
  await page.waitForTimeout(3000);

  // Complete verification with CI activation code
  await loginPage.completeRegistrationVerification(TEST_CREDENTIALS.CI_ACTIVATION_CODE);

  // Wait for successful login (redirect to machines page)
  await page.waitForURL('**/machines', { timeout: 30000 });

  console.warn(`[Setup] User registered and logged in for ${browser}`);

  // Save authentication state to browser-specific file
  const authFile = `${AUTH_DIR}/${browser}-state.json`;
  await page.context().storageState({ path: authFile });

  console.warn(`[Setup] Auth state saved to ${authFile}`);
});
