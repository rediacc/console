import { test } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';
import { createTeamViaUI } from '@/test-helpers/team-helpers';

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
    const teamName = `e2e-team-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

    testReporter.startStep('Navigate to Organization Teams section');

    // Navigate to Organization > Teams
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationTeams();
    await createTeamViaUI(page, teamName);

    testReporter.completeStep('Create new team', 'passed');

    await testReporter.finalizeTest();
  });
});
