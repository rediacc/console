import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';

// Skip: These tests require subscription plan that supports permission management.
// The COMMUNITY plan (default for E2E test users) returns 402 Payment Required.
// TODO: Update E2E setup to use a subscription plan with permission management features.
test.describe
  .skip('Permission Session Tests', () => {
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

    test('should check permission sessions @system @organization @access @session @regression', async ({
      page,
      screenshotManager: _screenshotManager,
      testReporter,
    }) => {
      testReporter.startStep('Navigate to Organization Access section');

      await page.getByTestId('main-nav-organization').click();
      await page.getByTestId('main-nav-organization-access').click();

      testReporter.completeStep('Navigate to Organization Access section', 'passed');

      testReporter.startStep('Check permission sessions');

      await page.getByRole('tab', { name: 'Sessions' }).click();
      await expect(page.getByTestId('sessions-stat-total')).toBeVisible();
      await page.getByTestId('sessions-stat-total').click();

      // Return to Permissions tab
      await page
        .locator('div')
        .filter({ hasText: /^Permissions$/ })
        .first()
        .click();

      testReporter.completeStep('Check permission sessions', 'passed');

      await testReporter.finalizeTest();
    });
  });
