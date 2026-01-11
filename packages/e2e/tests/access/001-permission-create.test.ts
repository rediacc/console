import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

test.describe('Permission Creation Tests', () => {
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

    test('should create new permission group @system @organization @access @regression', async ({
        page,
        screenshotManager,
        testReporter
    }) => {
        const stepNavigate = await testReporter.startStep('Navigate to Organization Access section');

        await page.getByTestId('main-nav-organization-access').click();
        
        await testReporter.completeStep('Navigate to Organization Access section', 'passed');

        const stepCreate = await testReporter.startStep('Create new permission group');

        await page.getByTestId('system-create-permission-group-button').click();
        await page.getByTestId('system-permission-group-name-input').click();
        await page.getByTestId('system-permission-group-name-input').fill('test-PERMISSION');
        await page.getByTestId('modal-create-permission-group-ok').click();
        await expect(page.getByText('test-PERMISSION')).toBeVisible();

        await testReporter.completeStep('Create new permission group', 'passed');

        await testReporter.finalizeTest();
    });
});
