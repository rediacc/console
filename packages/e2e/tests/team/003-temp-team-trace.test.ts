import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { test, expect } from '../../src/base/BaseTest';
import { E2E_DEFAULTS } from '../../src/utils/constants';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

// Skip: TestDataManager requires VM_WORKER_IPS which is not set in CI
test.describe
  .skip('Team Trace Tests', () => {
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

    test('should trace team audit records @system @organization @audit @regression', async ({
      page,
      screenshotManager: _screenshotManager,
      testReporter,
    }) => {
      testReporter.startStep('Navigate to Organization Users section');

      // Get created user
      const createdUser = testDataManager.getCreatedUser();

      //organization
      await page.getByTestId(TeamPageIDS.mainNavOrganization).click();

      // user table
      await page.getByTestId(TeamPageIDS.subNavOrganizationUsers).click();
      await expect(page.getByRole('cell', { name: `user ${createdUser.email}` })).toBeVisible();

      testReporter.completeStep('Navigate to Organization Users section', 'passed');

      testReporter.startStep('Trace team audit records');

      await page.getByTestId(TeamPageIDS.systemTeamTraceButton('test-TEAM-2')).click();
      const auditRecordsText = await page
        .getByTestId(TeamPageIDS.auditTraceTotalRecords)
        .textContent();
      const recordCount = Number.parseInt(auditRecordsText ?? E2E_DEFAULTS.CPU_COUNT_STRING);
      expect(recordCount).toBeGreaterThan(0);
      await page.getByRole('button', { name: 'Close' }).click();

      testReporter.completeStep('Trace team audit records', 'passed');

      await testReporter.finalizeTest();
    });
  });
