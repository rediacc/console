import { test as setup } from '@playwright/test';
import { API_DEFAULTS, TEST_CREDENTIALS } from '@rediacc/shared';
import { saveGlobalState } from '../../src/setup/global-state';
import { getEnvVarWithDefault } from '../../src/utils/env';
import { waitForNetworkIdleWithRetry } from '../../src/utils/retry';

/**
 * Global setup test that registers a unique user before all other tests.
 * Uses project dependencies so the web server is available.
 * NOTE: E2E navigation should go through the UI menu, not direct URL jumps,
 * to avoid losing session state on some mobile/device flows.
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

  // Track all network requests for debugging Windows timeout issue
  const pendingRequests = new Set<string>();
  page.on('request', (request) => {
    const url = request.url();
    pendingRequests.add(url);
    console.warn(`[Network] → Request: ${request.method()} ${url}`);
  });
  page.on('response', (response) => {
    const url = response.url();
    pendingRequests.delete(url);
    console.warn(`[Network] ← Response: ${response.status()} ${url} (${response.statusText()})`);
  });
  page.on('requestfailed', (request) => {
    const url = request.url();
    pendingRequests.delete(url);
    console.warn(`[Network] ✗ Failed: ${request.failure()?.errorText} ${url}`);
  });

  const baseURL = process.env.E2E_BASE_URL ?? API_DEFAULTS.CONSOLE_URL;
  const loginUrl = `${baseURL}login`;

  console.warn(`[Setup] Navigating to: ${loginUrl}`);

  // Navigate to login page with extended timeout for test mode (Vite compilation)
  const startNav = Date.now();
  await page.goto(loginUrl, { timeout: 60000, waitUntil: 'domcontentloaded' });
  console.warn(`[Setup] Page loaded in ${Date.now() - startNav}ms, waiting for network idle...`);
  console.warn(`[Setup] Pending requests: ${pendingRequests.size}`);
  if (pendingRequests.size > 0) {
    console.warn(`[Setup] Pending URLs: ${Array.from(pendingRequests).join(', ')}`);
  }

  const startIdle = Date.now();
  await waitForNetworkIdleWithRetry(page, '[data-testid="login-register-link"]', {
    maxRetries: 3,
    retryDelay: 2000,
    timeout: 15000,
  });
  console.warn(`[Setup] Network idle achieved in ${Date.now() - startIdle}ms`);

  // Click register link and wait for registration form to appear
  console.warn('[Setup] Clicking register link...');
  await page.locator('[data-testid="login-register-link"]').click();
  await page
    .locator('[data-testid="registration-organization-input"]')
    .waitFor({ state: 'visible' });
  console.warn('[Setup] Registration form visible');

  // Fill registration form
  console.warn('[Setup] Filling registration form...');
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
  console.warn('[Setup] Form filled, ready to submit');

  // Submit registration and wait for verification step
  // Note: Extended timeout (90s) for Windows Cloudflare tunnel latency
  // Registration API can take 60s+ with retries on Windows (health check + registration + retries)
  console.warn('[Setup] Submitting registration...');
  console.warn(`[Setup] Pending requests before submit: ${pendingRequests.size}`);
  if (pendingRequests.size > 0) {
    console.warn(`[Setup] Pending URLs: ${Array.from(pendingRequests).join(', ')}`);
  }

  const startSubmit = Date.now();
  await page.locator('[data-testid="registration-submit-button"]').click();

  console.warn('[Setup] Registration submitted, waiting for activation code input...');
  console.warn(`[Setup] Pending requests after submit: ${pendingRequests.size}`);
  if (pendingRequests.size > 0) {
    console.warn(`[Setup] Pending URLs: ${Array.from(pendingRequests).join(', ')}`);
  }

  // Log pending requests every 10 seconds while waiting
  const logInterval = setInterval(() => {
    const elapsed = Date.now() - startSubmit;
    console.warn(`[Setup] Still waiting for activation input... ${elapsed}ms elapsed`);
    console.warn(`[Setup] Pending requests: ${pendingRequests.size}`);
    if (pendingRequests.size > 0) {
      console.warn(`[Setup] Pending URLs: ${Array.from(pendingRequests).join(', ')}`);
    }
  }, 10000);

  try {
    await page
      .locator('[data-testid="registration-activation-code-input"]')
      .waitFor({ state: 'visible', timeout: 90000 });
    const submitDuration = Date.now() - startSubmit;
    console.warn(`[Setup] Activation code input visible after ${submitDuration}ms`);
  } finally {
    clearInterval(logInterval);
  }

  // Enter verification code (AAA111 in test mode)
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
