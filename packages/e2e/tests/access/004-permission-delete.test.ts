import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';

// Skip: These tests require subscription plan that supports permission management.
// The COMMUNITY plan (default for E2E test users) returns 402 Payment Required.
// TODO: Update E2E setup to use a subscription plan with permission management features.
test.describe.skip('Permission Delete Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    // Set expert mode BEFORE page load (localStorage is read on app initialization)
    await page.addInitScript(() => {
      localStorage.setItem('uiMode', 'expert');
    });

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should delete permission group @system @organization @access @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    testReporter.startStep('Navigate to Organization Access section');

    const nav = new NavigationHelper(page);
    await nav.goToOrganizationAccess();

    testReporter.completeStep('Navigate to Organization Access section', 'passed');

    testReporter.startStep('Delete permission group');

    await page.getByTestId('system-permission-group-delete-button-test-PERMISSION').click();
    await page.getByRole('button', { name: 'Yes' }).click();
    await expect(page.getByText('test-PERMISSION')).not.toBeVisible();

    testReporter.completeStep('Delete permission group', 'passed');

    await testReporter.finalizeTest();
  });
});
