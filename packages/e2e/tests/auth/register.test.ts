import { test, expect } from '../../src/base/BaseTest';
import { LoginPage } from '../../pages/auth/LoginPage';
import { requireEnvVar } from '@/utils/env';

test.describe('Registration Tests', () => {
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
  });

  test('should register new account @auth', async ({ page, testReporter }) => {
    const step1 = await testReporter.startStep('Navigate to registration page');

    await loginPage.navigate();
    await loginPage.clickRegister();

    await testReporter.completeStep('Navigate to registration page', 'passed');

    const step2 = await testReporter.startStep('Fill registration form');

    const timestamp = Date.now();
    const organizationName = `E2E Test Organization ${timestamp}`;
    //const organizationName = requireEnvVar('TEST_USER_COMPANY');
    const email = requireEnvVar('TEST_USER_EMAIL');
    const password = requireEnvVar('TEST_USER_PASSWORD');
    const verificationCode = requireEnvVar('TEST_VERIFICATION_CODE');

    await loginPage.fillRegistrationForm(organizationName, email, password, password, true);

    await testReporter.completeStep('Fill registration form', 'passed');

    const step3 = await testReporter.startStep('Submit registration form');

    await loginPage.submitRegistrationForm();
    await page.waitForTimeout(3000);

    await loginPage.completeRegistrationVerification(verificationCode);

    await testReporter.completeStep('Submit registration form', 'passed');

    await testReporter.finalizeTest();
  });
});
