import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { test } from '../../src/base/BaseTest';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

// Skip: TestDataManager requires VM_WORKER_IPS which is not set in CI
test.describe
  .skip('Team Creation Tests', () => {
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
      testReporter.startStep('Navigate to Organization Users section');

      await page.getByTestId(TeamPageIDS.mainNavOrganization).click();
      await page.getByTestId(TeamPageIDS.subNavOrganizationTeams).click();
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
