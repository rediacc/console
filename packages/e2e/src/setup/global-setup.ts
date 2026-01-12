import { chromium, firefox, webkit, type FullConfig, type Browser } from '@playwright/test';
import { API_DEFAULTS, TEST_CREDENTIALS } from '@rediacc/shared';
import { saveGlobalState } from './global-state';

/**
 * Launch a browser based on what's installed.
 * In CI, only the specific browser for that job is installed.
 */
async function launchAvailableBrowser(): Promise<Browser> {
  // Try browsers in order of preference
  const browsers = [
    { name: 'chromium', launcher: chromium },
    { name: 'firefox', launcher: firefox },
    { name: 'webkit', launcher: webkit },
  ];

  for (const { name, launcher } of browsers) {
    try {
      const browser = await launcher.launch({ headless: true });
      console.warn(`[Setup] Using ${name} browser`);
      return browser;
    } catch {
      // Browser not installed, try next
    }
  }

  throw new Error('No browser available. Run: npx playwright install');
}

async function globalSetup(config: FullConfig): Promise<void> {
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

  const baseURL = config.projects[0]?.use?.baseURL ?? API_DEFAULTS.CONSOLE_URL;
  const browser = await launchAvailableBrowser();
  const page = await browser.newPage();

  try {
    // Navigate to login page
    await page.goto(`${baseURL}login`);
    await page.waitForLoadState('networkidle');

    // Click register link
    await page.locator('[data-testid="login-register-link"]').click();
    await page.waitForTimeout(1000);

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

    // Submit registration
    await page.locator('[data-testid="registration-submit-button"]').click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Enter verification code (111111 in CI mode)
    await page
      .locator('[data-testid="registration-activation-code-input"]')
      .fill(TEST_CREDENTIALS.CI_ACTIVATION_CODE);
    await page.locator('[data-testid="registration-verify-button"]').click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Save credentials for tests to use
    saveGlobalState({
      email: credentials.email,
      password: credentials.password,
      organizationName: credentials.organizationName,
      createdAt: new Date().toISOString(),
    });

    console.warn('[Setup] Registration complete');
    console.warn('='.repeat(60));
  } catch (error) {
    console.error('[Setup] Failed!', error);
    await page.screenshot({ path: 'reports/e2e/setup-failure.png' });
    throw error;
  } finally {
    await browser.close();
  }
}

export default globalSetup;
