import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { test } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

test.describe('Team Creation Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;
  let _testDataManager: TestDataManager;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
    _testDataManager = new TestDataManager();

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should create new team with permissions @system @organization @teams @regression', async ({
    page,
    testReporter,
  }) => {
    testReporter.startStep('Navigate to Organization Teams section');

    // Navigate to Organization > Teams
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationTeams();

    await page.getByTestId(TeamPageIDS.systemCreateTeamButton).click();
    await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).click();
    await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).fill('test-TEAM');
    await page.getByTestId(TeamPageIDS.vaultEditorGenerateSshPrivateKey).click();
    await page.getByTestId(TeamPageIDS.vaultEditorGenerateButton).click();
    await page.getByTestId(TeamPageIDS.vaultEditorApplyGenerated).click();
    await page.getByTestId(TeamPageIDS.resourceModalOkButton).click();

    testReporter.completeStep('Create new team', 'passed');

    await testReporter.finalizeTest();
  });
});
