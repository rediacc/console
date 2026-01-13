import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { createTeamViaUI } from '../helpers/team-helpers';
import { ensureCreatedUser } from '../helpers/user-helpers';

test.describe('Team Edit Tests', () => {
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

  test('should edit team name and view members @system @organization @teams @regression', async ({
    page,
    testReporter,
  }) => {
    const baseTeamName = `e2e-team-${Date.now()}`;
    const updatedTeamName = `${baseTeamName}-updated`;

    testReporter.startStep('Navigate to Organization Users section');

    const createdUser = await ensureCreatedUser(page, testDataManager);

    // Navigate to Organization > Users
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    await expect(page.getByTestId(UserPageIDs.resourceListItem(createdUser.email))).toBeVisible();

    testReporter.completeStep('Navigate to Organization Users section', 'passed');

    testReporter.startStep('Edit team name and view members');

    await createTeamViaUI(page, baseTeamName);

    await page.getByTestId(TeamPageIDS.systemTeamEditButton(baseTeamName)).click();
    await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).click();
    await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).fill(updatedTeamName);
    await page.getByTestId(TeamPageIDS.resourceModalOkButton).click();
    await page.getByTestId(TeamPageIDS.systemTeamMembersButton(updatedTeamName)).click();

    testReporter.completeStep('Edit team name and view members', 'passed');

    await testReporter.finalizeTest();
  });
});
