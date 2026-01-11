import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';

test.describe('Permission Creation Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should create new permission group @system @organization @access @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    testReporter.startStep('Navigate to Organization Access section');

    await page.getByTestId('main-nav-organization-access').click();

    testReporter.completeStep('Navigate to Organization Access section', 'passed');

    testReporter.startStep('Create new permission group');

    await page.getByTestId('system-create-permission-group-button').click();
    await page.getByTestId('system-permission-group-name-input').click();
    await page.getByTestId('system-permission-group-name-input').fill('test-PERMISSION');
    await page.getByTestId('modal-create-permission-group-ok').click();
    await expect(page.getByText('test-PERMISSION')).toBeVisible();

    testReporter.completeStep('Create new permission group', 'passed');

    await testReporter.finalizeTest();
  });
});
