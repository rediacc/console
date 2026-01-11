import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

test.describe('Permission Delete Tests', () => {
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

    test('should delete permission group @system @organization @access @regression', async ({
        page,
        screenshotManager,
        testReporter
    }) => {
        const stepNavigate = await testReporter.startStep('Navigate to Organization Access section');

        await page.getByTestId('main-nav-organization-access').click();
        
        await testReporter.completeStep('Navigate to Organization Access section', 'passed');

        const stepDelete = await testReporter.startStep('Delete permission group');

        await page.getByTestId('system-permission-group-delete-button-test-PERMISSION').click();
        await page.getByRole('button', { name: 'Yes' }).click();
        await expect(page.getByText('test-PERMISSION')).not.toBeVisible();

        await testReporter.completeStep('Delete permission group', 'passed');

        await testReporter.finalizeTest();
    });
});
