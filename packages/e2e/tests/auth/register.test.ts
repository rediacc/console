import { requireEnvVar } from '@/utils/env';
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
    const email = requireEnvVar('TEST_USER_EMAIL');
    const password = requireEnvVar('TEST_USER_PASSWORD');
    const verificationCode = requireEnvVar('TEST_VERIFICATION_CODE');

    await loginPage.fillRegistrationForm(organizationName, email, password, password, true);

    testReporter.completeStep('Fill registration form', 'passed');

    testReporter.startStep('Submit registration form');

    await loginPage.submitRegistrationForm();
    await page.waitForTimeout(3000);

    await loginPage.completeRegistrationVerification(verificationCode);

    testReporter.completeStep('Submit registration form', 'passed');

    await testReporter.finalizeTest();
  });
});
