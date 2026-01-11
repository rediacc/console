import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

test.describe('Permission Edit Tests', () => {
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

    test('should edit permission group permissions and assign user @system @organization @access @regression', async ({
        page,
        screenshotManager,
        testReporter
    }) => {
        const stepNavigate = await testReporter.startStep('Navigate to Organization Access section');

        await page.getByTestId('main-nav-organization-access').click();
        await expect(page.getByText('test-PERMISSION')).toBeVisible();

        await testReporter.completeStep('Navigate to Organization Access section', 'passed');

        const stepManage = await testReporter.startStep('Manage permissions');
        
        await page.getByTestId('system-permission-group-manage-button-test-PERMISSION').click();
        await page.getByRole('tab', { name: 'Add Permissions' }).click();
        await page.locator('.ant-select.ant-select-outlined.flex-1 > .ant-select-selector > .ant-select-selection-wrap > .ant-select-selection-item').click();
        await page.getByRole('tab', { name: 'Current Permissions' }).click();
        await page.getByRole('listitem').nth(5).click();
        await page.locator('.ant-list-item-meta').click();
        await page.getByRole('tab', { name: 'Add Permissions' }).click();
        await page.locator('.ant-select.ant-select-outlined.flex-1 > .ant-select-selector > .ant-select-selection-wrap > .ant-select-selection-item').click();
        await page.getByRole('button', { name: 'Close' }).click();

        await testReporter.completeStep('Manage permissions', 'passed');

        const stepAssign = await testReporter.startStep('Assign user to permission group');

        await page.getByTestId('system-permission-group-assign-user-button-test-PERMISSION').click();
        await page.locator('.ant-select.ant-select-outlined.w-full > .ant-select-selector > .ant-select-selection-wrap > .ant-select-selection-item').click();
        await page.getByRole('button', { name: 'Close' }).click();

        await testReporter.completeStep('Assign user to permission group', 'passed');

        await testReporter.finalizeTest();
    });
});
