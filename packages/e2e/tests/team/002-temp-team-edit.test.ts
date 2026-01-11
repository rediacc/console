import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';

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
        testReporter
    }) => {
        const stepNavigate = await testReporter.startStep('Navigate to Organization Users section');

        // Get created user
        const createdUser = testDataManager.getCreatedUser();

        // Navigate to users
        await page.getByTestId(TeamPageIDS.mainNavOrganizationUsers).click();
        await expect(page.getByRole('cell', { name: `user ${createdUser.email}` })).toBeVisible();

        await testReporter.completeStep('Navigate to Organization Users section', 'passed');

        const stepEditTeam = await testReporter.startStep('Edit team name and view members');

        await page.getByTestId(TeamPageIDS.systemTeamEditButton('test-TEAM')).click();
        await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).click();
        await page.getByTestId(TeamPageIDS.resourceModalFieldTeamNameInput).fill('test-TEAM-2');
        await page.getByTestId(TeamPageIDS.resourceModalOkButton).click();
        await page.getByTestId(TeamPageIDS.systemTeamMembersButton('test-TEAM-2')).click();

        await testReporter.completeStep('Edit team name and view members', 'passed');

        await testReporter.finalizeTest();
    });
});
