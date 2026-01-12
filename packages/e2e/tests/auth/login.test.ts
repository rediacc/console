import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';
import { loadGlobalState } from '../../src/setup/global-state';

test.describe('Login Tests', () => {
  let loginPage: LoginPage;
  let dashboardPage: DashboardPage;

  test.beforeEach(({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
  });

  test('should login with valid credentials @auth', async ({ page, testReporter }) => {
    testReporter.startStep('Navigate to login page');

    await loginPage.navigate();
    await loginPage.verifyFormValidation();

    testReporter.completeStep('Navigate to login page', 'passed');

    testReporter.startStep('Enter valid credentials');

    const state = loadGlobalState();
    await loginPage.login(state.email, state.password);
    testReporter.completeStep('Enter valid credentials', 'passed');

    testReporter.startStep('Verify successful login');

    await loginPage.waitForLoginCompletion();
    await dashboardPage.verifyDashboardLoaded();

    expect(page.url()).toContain('/machines');

    testReporter.completeStep('Verify successful login', 'passed');

    await testReporter.finalizeTest();
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

  test('should navigate to registration page @auth', async ({ page, testReporter }) => {
    testReporter.startStep('Navigate to login page');
    await loginPage.navigate();
    testReporter.completeStep('Navigate to login page', 'passed');

    testReporter.startStep('Click register link');

    await loginPage.clickRegister();

    // Wait for registration form to appear
    await page
      .locator('[data-testid="registration-organization-input"]')
      .waitFor({ state: 'visible' });

    testReporter.completeStep('Click register link', 'passed');

    await testReporter.finalizeTest();
  });
});
