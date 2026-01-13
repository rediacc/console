import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { E2E_DEFAULTS } from '../../src/utils/constants';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { ensureCreatedUser } from '../helpers/user-helpers';

test.describe('Team Trace Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;
  let testDataManager: TestDataManager;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
    testDataManager = new TestDataManager();

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should trace team user audit records @system @organization @audit @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    testReporter.startStep('Navigate to Organization Users section');

    const createdUser = await ensureCreatedUser(page, testDataManager);

    // Navigate to Organization > Users
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    await expect(page.getByTestId(UserPageIDs.resourceListItem(createdUser.email))).toBeVisible();

    testReporter.completeStep('Navigate to Organization Users section', 'passed');

    testReporter.startStep('Trace user audit records');

    await page.getByTestId(UserPageIDs.systemUserTraceButton(createdUser.email)).click();
    const auditRecordsText = await page
      .getByTestId(UserPageIDs.auditTraceVisibleRecords)
      .locator('strong')
      .textContent();
    const recordCount = Number.parseInt(auditRecordsText ?? E2E_DEFAULTS.CPU_COUNT_STRING);
    expect(recordCount).toBeGreaterThan(0);
    const auditModal = page.getByTestId('audit-trace-modal');
    await auditModal.getByRole('button', { name: 'Close' }).click();
    testReporter.completeStep('Trace user audit records', 'passed');
    await testReporter.finalizeTest();
  });
});
