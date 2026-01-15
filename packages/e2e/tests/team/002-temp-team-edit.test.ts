import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { test } from '../../src/base/BaseTest';
import { createTeamViaUI, waitForTeamRow } from '../helpers/team-helpers';

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

    const teamRow = await waitForTeamRow(page, baseTeamName);
    await teamRow.scrollIntoViewIfNeeded();
    const editButton = page.getByTestId(TeamPageIDS.systemTeamEditButton(baseTeamName));
    if (await editButton.isVisible().catch(() => false)) {
      await editButton.click();
    } else {
      const actionsButton = teamRow.getByRole('button', { name: /actions/i });
      await actionsButton.click();
      await page.getByRole('menuitem', { name: /edit/i }).click();
    }
    await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).click();
    await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).fill(updatedTeamName);
    await page.getByTestId(TeamPageIDS.resourceModalOkButton).click();
    const updatedRow = await waitForTeamRow(page, updatedTeamName);
    await updatedRow.scrollIntoViewIfNeeded();
    const membersButton = page.getByTestId(TeamPageIDS.systemTeamMembersButton(updatedTeamName));
    if (await membersButton.isVisible().catch(() => false)) {
      await membersButton.click();
    } else {
      const actionsButton = updatedRow.getByRole('button', { name: /actions/i });
      await actionsButton.click();
      await page.getByRole('menuitem', { name: /members/i }).click();
    }

    testReporter.completeStep('Edit team name and view members', 'passed');

    await testReporter.finalizeTest();
  });
});
