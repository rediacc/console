import { test, expect } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';
import { loadGlobalState } from '@/setup/global-state';

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
});
