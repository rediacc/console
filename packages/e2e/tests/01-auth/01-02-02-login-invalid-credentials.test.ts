import { test } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';

test.describe('Login Tests - Invalid Credentials', () => {
  let loginPage: LoginPage;

  test.beforeEach(({ page }) => {
    loginPage = new LoginPage(page);
  });

  test('should show error with invalid credentials @auth', async ({ testReporter }) => {
    testReporter.startStep('Navigate to login page');
    await loginPage.navigate();
    testReporter.completeStep('Navigate to login page', 'passed');

    testReporter.startStep('Enter invalid credentials');

    await loginPage.login('invalid@example.com', 'wrongpassword');

    testReporter.completeStep('Enter invalid credentials', 'passed');

    testReporter.startStep('Verify error message');

    await loginPage.validateErrorMessage('not found');

    testReporter.completeStep('Verify error message', 'passed');

    await testReporter.finalizeTest();
  });
});
