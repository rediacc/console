import { TEST_CREDENTIALS } from '@rediacc/shared';
import { getEnvVarWithDefault } from '@/utils/env';
import { LoginPage } from '../../pages/auth/LoginPage';
import { test } from '../../src/base/BaseTest';

test.describe('Registration Tests', () => {
  let loginPage: LoginPage;

  test.beforeEach(({ page }) => {
    loginPage = new LoginPage(page);
  });

  test('should register new account @auth', async ({ page, testReporter }) => {
    testReporter.startStep('Navigate to registration page');

    await loginPage.navigate();
    await loginPage.clickRegister();

    testReporter.completeStep('Navigate to registration page', 'passed');

    testReporter.startStep('Fill registration form');

    const timestamp = Date.now();
    const organizationName = `E2E Test Organization ${timestamp}`;
    // Use unique email for registration (not admin email which already exists)
    const email = `e2e-register-${timestamp}@${TEST_CREDENTIALS.TEST_EMAIL_DOMAIN}`;
    const verificationCode = getEnvVarWithDefault('TEST_VERIFICATION_CODE');

    // Use complex password that meets requirements (8+ chars, upper/lower, number, special char)
    await loginPage.fillRegistrationForm(
      organizationName,
      email,
      TEST_CREDENTIALS.TEST_PASSWORD,
      TEST_CREDENTIALS.TEST_PASSWORD,
      true
    );

    testReporter.completeStep('Fill registration form', 'passed');

    testReporter.startStep('Submit registration form');

    await loginPage.submitRegistrationForm();

    // Check for API error before waiting for verification step
    // This provides a clear error message instead of a generic timeout
    const errorAlert = page.locator('.ant-alert-error');
    if (await errorAlert.isVisible({ timeout: 2000 }).catch(() => false)) {
      const errorText = await errorAlert.textContent();
      throw new Error(`Registration API failed: ${errorText}`);
    }

    // Wait for verification step to appear
    await page
      .locator('[data-testid="registration-activation-code-input"]')
      .waitFor({ state: 'visible', timeout: 30000 });

    await loginPage.completeRegistrationVerification(verificationCode);

    testReporter.completeStep('Submit registration form', 'passed');

    await testReporter.finalizeTest();
  });
});
