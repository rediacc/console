import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';
import { E2E_DEFAULTS } from '../../src/utils/constants';

test.describe('Permission Trace Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

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

    await page.getByTestId('main-nav-organization-access').click();

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
