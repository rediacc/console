import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { E2E_DEFAULTS } from '../../src/utils/constants';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { createTeamViaUI } from '../helpers/team-helpers';
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

  test('should trace team audit records @system @organization @audit @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    const teamName = `e2e-team-${Date.now()}`;

    testReporter.startStep('Navigate to Organization Users section');

    const createdUser = await ensureCreatedUser(page, testDataManager);

    // Navigate to Organization > Users
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    await expect(page.getByTestId(UserPageIDs.resourceListItem(createdUser.email))).toBeVisible();

    testReporter.completeStep('Navigate to Organization Users section', 'passed');

    testReporter.startStep('Trace team audit records');

    await createTeamViaUI(page, teamName);
    await page.getByTestId(TeamPageIDS.systemTeamTraceButton(teamName)).click();
    const auditRecordsText = await page
      .getByTestId(TeamPageIDS.auditTraceTotalRecords)
      .locator('strong')
      .textContent();
    const recordCount = Number.parseInt(auditRecordsText ?? E2E_DEFAULTS.CPU_COUNT_STRING);
    expect(recordCount).toBeGreaterThan(0);
    await page.getByRole('button', { name: 'Close' }).click();

    testReporter.completeStep('Trace team audit records', 'passed');

    await testReporter.finalizeTest();
  });
});
