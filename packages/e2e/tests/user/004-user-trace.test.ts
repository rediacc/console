import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { UserPageIDs } from '../../pages/user/UserPageIDs';

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

    test('should trace team user audit records @system @organization @audit @regression', async ({
        page,
        screenshotManager,
        testReporter
    }) => {
        const stepNavigate = await testReporter.startStep('Navigate to Organization Users section');

        // Get created user
        const createdUser = testDataManager.getCreatedUser();

        //organization
        await page.getByTestId(UserPageIDs.mainNavOrganization).click();

        // user table
        await page.getByTestId(UserPageIDs.mainNavOrganizationUsers).click();
        await expect(page.getByRole('cell', { name: `user ${createdUser.email}` })).toBeVisible();

        await testReporter.completeStep('Navigate to Organization Users section', 'passed');

        const stepTraceUser = await testReporter.startStep('Trace user audit records');

        await page.getByTestId(UserPageIDs.systemUserTraceButton(createdUser.email)).click();
        const auditRecordsText = await page.getByTestId(UserPageIDs.auditTraceVisibleRecords).textContent();
        const recordCount = parseInt(auditRecordsText || '0');
        expect(recordCount).toBeGreaterThan(0);
        await page.getByRole('button', { name: 'Close' }).click();
        await testReporter.completeStep('Trace user audit records', 'passed');
        await testReporter.finalizeTest();
    });
});
