import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { test } from '../../src/base/BaseTest';
import { createTeamViaUI } from '../helpers/team-helpers';

test.describe('Team Edit Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

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
