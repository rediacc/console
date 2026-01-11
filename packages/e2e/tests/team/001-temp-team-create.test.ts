import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';

test.describe('Team Creation Tests', () => {
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

    test('should create new team with permissions @system @organization @teams @regression', async ({
        page,
        testReporter
    }) => {
        const stepNavigate = await testReporter.startStep('Navigate to Organization Users section');
        
        await page.getByTestId(TeamPageIDS.mainNavOrganization).click();
        await page.getByTestId(TeamPageIDS.mainNavOrganizationTeams).click();
        await page.getByTestId(TeamPageIDS.systemCreateTeamButton).click();
        await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).click();
        await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).fill('test-TEAM');
        await page.getByTestId(TeamPageIDS.vaultEditorGenerateSshPrivateKey).click();
        await page.getByTestId(TeamPageIDS.vaultEditorGenerateButton).click();
        await page.getByTestId(TeamPageIDS.vaultEditorApplyGenerated).click();
        await page.getByTestId(TeamPageIDS.resourceModalOkButton).click();

        await testReporter.completeStep('Create new team', 'passed');

        await testReporter.finalizeTest();
    });
});
