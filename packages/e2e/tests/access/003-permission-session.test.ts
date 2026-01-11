import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

test.describe('Permission Session Tests', () => {
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

    test('should check permission sessions @system @organization @access @session @regression', async ({
        page,
        screenshotManager,
        testReporter
    }) => {
        const stepNavigate = await testReporter.startStep('Navigate to Organization Access section');

        await page.getByTestId('main-nav-organization-access').click();
        
        await testReporter.completeStep('Navigate to Organization Access section', 'passed');

        const stepSession = await testReporter.startStep('Check permission sessions');

        await page.getByRole('tab', { name: 'Sessions' }).click();
        await expect(page.getByTestId('sessions-stat-total')).toBeVisible();
        await page.getByTestId('sessions-stat-total').click();
        
        // Return to Permissions tab
        await page.locator('div').filter({ hasText: /^Permissions$/ }).first().click();

        await testReporter.completeStep('Check permission sessions', 'passed');

        await testReporter.finalizeTest();
    });
});
