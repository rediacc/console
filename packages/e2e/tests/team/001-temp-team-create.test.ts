import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { createTeamViaUI } from '../helpers/team-helpers';

test.describe('Team Creation Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should create new team with permissions @system @organization @teams @regression', async ({
    page,
    testReporter,
  }) => {
    const teamName = `e2e-team-${Date.now()}`;

    testReporter.startStep('Navigate to Organization Teams section');

    // Navigate to Organization > Teams
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationTeams();
    await createTeamViaUI(page, teamName);

    testReporter.completeStep('Create new team', 'passed');

    await testReporter.finalizeTest();
  });
});
