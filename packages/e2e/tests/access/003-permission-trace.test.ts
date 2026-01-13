import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { E2E_DEFAULTS } from '../../src/utils/constants';

// Skip: These tests require subscription plan that supports permission management.
// The COMMUNITY plan (default for E2E test users) returns 402 Payment Required.
// TODO: Update E2E setup to use a subscription plan with permission management features.
test.describe.skip('Permission Trace Tests', () => {
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

  test('should trace permission group audit records @system @organization @access @audit @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    testReporter.startStep('Navigate to Organization Access section');

    const nav = new NavigationHelper(page);
    await nav.goToOrganizationAccess();

    testReporter.completeStep('Navigate to Organization Access section', 'passed');

    testReporter.startStep('Trace permission group audit records');

    await page.getByTestId('system-permission-group-trace-button-test-PERMISSION').click();
    const auditRecordsText = await page.getByTestId('audit-trace-total-records').textContent();
    const recordCount = Number.parseInt(auditRecordsText ?? E2E_DEFAULTS.CPU_COUNT_STRING);
    expect(recordCount).toBeGreaterThan(0);

    await page.getByRole('button', { name: 'Close' }).click();

    testReporter.completeStep('Trace permission group audit records', 'passed');

    await testReporter.finalizeTest();
  });
});
