import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

test.describe('Permission Trace Tests', () => {
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

    test('should trace permission group audit records @system @organization @access @audit @regression', async ({
        page,
        screenshotManager,
        testReporter
    }) => {
        const stepNavigate = await testReporter.startStep('Navigate to Organization Access section');

        await page.getByTestId('main-nav-organization-access').click();
        
        await testReporter.completeStep('Navigate to Organization Access section', 'passed');

        const stepTrace = await testReporter.startStep('Trace permission group audit records');

        await page.getByTestId('system-permission-group-trace-button-test-PERMISSION').click();
        const auditRecordsText = await page.getByTestId('audit-trace-total-records').textContent();
        const recordCount = parseInt(auditRecordsText || '0');
        expect(recordCount).toBeGreaterThan(0);
        
        await page.getByRole('button', { name: 'Close' }).click();

        await testReporter.completeStep('Trace permission group audit records', 'passed');

        await testReporter.finalizeTest();
    });
});
