import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';

// Skip: These tests require subscription plan that supports permission management.
// The COMMUNITY plan (default for E2E test users) returns 402 Payment Required.
// TODO: Update E2E setup to use a subscription plan with permission management features.
test.describe
  .skip('Permission Creation Tests', () => {
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

    test('should create new permission group @system @organization @access @regression', async ({
      page,
      screenshotManager: _screenshotManager,
      testReporter,
    }) => {
      testReporter.startStep('Navigate to Organization Access section');

      const nav = new NavigationHelper(page);
      await nav.goToOrganizationAccess();

      testReporter.completeStep('Navigate to Organization Access section', 'passed');

      testReporter.startStep('Create new permission group');
      await page.getByTestId('system-create-permission-group-button').click();

      const nameInput = page.getByTestId('system-permission-group-name-input');
      await expect(nameInput).toBeVisible();
      await nameInput.fill('test-PERMISSION');
      await nameInput.press('Enter');

      await expect(
        page.getByTestId('system-permission-group-delete-button-test-PERMISSION')
      ).toBeVisible({ timeout: 15000 });
      testReporter.completeStep('Create new permission group', 'passed');

      await testReporter.finalizeTest();
    });
  });
