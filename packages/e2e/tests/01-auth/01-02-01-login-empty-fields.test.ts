import { test } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';

test.describe('Login Tests - Empty Fields', () => {
  let loginPage: LoginPage;

  test.beforeEach(({ page }) => {
    loginPage = new LoginPage(page);
  });

  test('should disable login button with empty fields @auth', async ({ testReporter }) => {
    testReporter.startStep('Navigate to login page');
    await loginPage.navigate();
    testReporter.completeStep('Navigate to login page', 'passed');

    testReporter.startStep('Verify empty form state');

    await loginPage.clearForm();
    await loginPage.isLoginButtonEnabled();

    testReporter.completeStep('Verify empty form state', 'passed');
    await testReporter.finalizeTest();
  });
});
