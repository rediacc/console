import { test as setup } from '@playwright/test';
import { API_DEFAULTS, TEST_CREDENTIALS } from '@rediacc/shared';
import { saveGlobalState } from '../../src/setup/global-state';
import { getEnvVarWithDefault } from '../../src/utils/env';
import { waitForNetworkIdleWithRetry } from '../../src/utils/retry';

/**
 * Global setup test that registers a unique user before all other tests.
 * Uses project dependencies so the web server is available.
 */
setup('register user for e2e tests', async ({ page }) => {
  const runId = Date.now();
  const credentials = {
    organizationName: `E2E Test Org ${runId}`,
    email: `e2e-${runId}@${TEST_CREDENTIALS.TEST_EMAIL_DOMAIN}`,
    password: TEST_CREDENTIALS.TEST_PASSWORD,
  };

  console.warn('='.repeat(60));
  console.warn('E2E Test Setup - Dynamic User Registration');
  console.warn('='.repeat(60));
  console.warn(`[Setup] Registering: ${credentials.email}`);

  const baseURL = process.env.E2E_BASE_URL ?? API_DEFAULTS.CONSOLE_URL;
  const loginUrl = `${baseURL}login`;

  console.warn(`[Setup] Navigating to: ${loginUrl}`);

  // Navigate to login page with extended timeout for test mode (Vite compilation)
  await page.goto(loginUrl, { timeout: 60000, waitUntil: 'domcontentloaded' });
  console.warn('[Setup] Page loaded, waiting for network idle...');
  await waitForNetworkIdleWithRetry(page, '[data-testid="login-register-link"]', {
    maxRetries: 3,
    retryDelay: 2000,
    timeout: 15000,
  });

  // Click register link and wait for registration form to appear
  await page.locator('[data-testid="login-register-link"]').click();
  await page
    .locator('[data-testid="registration-organization-input"]')
    .waitFor({ state: 'visible' });

  // Fill registration form
  await page
    .locator('[data-testid="registration-organization-input"]')
    .fill(credentials.organizationName);
  await page.locator('[data-testid="registration-email-input"]').fill(credentials.email);
  await page.locator('[data-testid="registration-password-input"]').fill(credentials.password);
  await page
    .locator('[data-testid="registration-password-confirm-input"]')
    .fill(credentials.password);

  // Check terms checkbox
  const termsCheckbox = page.locator('#termsAccepted');
  if (!(await termsCheckbox.isChecked())) {
    await termsCheckbox.check();
  }

  // Submit registration and wait for verification step
  await page.locator('[data-testid="registration-submit-button"]').click();
  await page
    .locator('[data-testid="registration-activation-code-input"]')
    .waitFor({ state: 'visible', timeout: 30000 });

  // Enter verification code (111111 in test mode)
  await page
    .locator('[data-testid="registration-activation-code-input"]')
    .fill(getEnvVarWithDefault('TEST_VERIFICATION_CODE'));
  await page.locator('[data-testid="registration-verify-button"]').click();
  await waitForNetworkIdleWithRetry(page, undefined, {
    maxRetries: 3,
    retryDelay: 2000,
    timeout: 15000,
  });

  // Save credentials for tests to use
  saveGlobalState({
    email: credentials.email,
    password: credentials.password,
    organizationName: credentials.organizationName,
    createdAt: new Date().toISOString(),
  });

  console.warn('[Setup] Registration complete');
  console.warn('='.repeat(60));
});
