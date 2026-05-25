import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';

test.describe('Audit Records Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();

    await page.getByTestId('user-menu-button').click();
    await page
      .getByTestId('main-mode-toggle')
      .locator('.ant-segmented-item')
      .nth(1)
      .click();
    await page.getByTestId('user-menu-button').click();
  });

  test.afterEach(async ({ testReporter }) => {
    await testReporter.finalizeTest();
  });

  test('should display audit records table with at least one row @smoke @audit @regression', async ({
    page,
    testReporter,
  }) => {
    test.setTimeout(120000);
    testReporter.startStep('Navigate to Audit page');

    const nav = new NavigationHelper(page);

    await page.getByTestId('user-menu-button').click();
    await page
      .getByTestId('main-mode-toggle')
      .locator('.ant-segmented-item')
      .nth(1)
      .click();
    await page.getByTestId('user-menu-button').click();


    // Wait for the audit navigation item to be visible before clicking
    const auditNavItem = page.getByTestId('main-nav-audit');
    await expect(auditNavItem).toBeVisible({ timeout: 15000 });

    await nav.goToAudit();

    const filterCard = page.getByTestId('audit-filter-card');
    await expect(filterCard).toBeVisible({ timeout: 15000 });

    testReporter.completeStep('Navigate to Audit page', 'passed');

    testReporter.startStep('Wait for audit table to load');

    const tableCard = page.getByTestId('audit-table-card');
    await expect(tableCard).toBeVisible({ timeout: 15000 });

    // Wait until the loading spinner is gone
    const loadingSpinner = tableCard.locator('.ant-spin-spinning');
    await expect(loadingSpinner).not.toBeVisible({ timeout: 45000 });

    testReporter.completeStep('Wait for audit table to load', 'passed');

    testReporter.startStep('Verify table has at least one row');

    const tableRows = tableCard.locator('.ant-table-tbody tr.ant-table-row');

    await expect
      .poll(
        async () => {
          return await tableRows.count();
        },
        { timeout: 15000, intervals: [1000, 2000, 3000, 5000] }
      )
      .toBeGreaterThanOrEqual(1);

    testReporter.completeStep('Verify table has at least one row', 'passed');
  });
});
