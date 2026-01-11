import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { UserPageIDs } from '../../pages/user/UserPageIDs';

test.describe('User Permission Tests', () => {
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

    test('should activate user @system @users @permissions @regression', async ({
        page,
        testReporter
    }) => {
        const tempUser = testDataManager.getUser('tempuser');
        const newUserEmail = tempUser.email;

        const stepNavigate = await testReporter.startStep('Navigate to Users section');
        await page.getByTestId(UserPageIDs.mainNavOrganization).click();
        await page.getByTestId(UserPageIDs.mainNavOrganizationUsers).click();
        const userTable = page.getByTestId(UserPageIDs.systemUserTable);
        await expect(userTable).toBeVisible({ timeout: 10000 });
        await testReporter.completeStep('Navigate to Users section', 'passed');

        const stepActivateUser = await testReporter.startStep('Activate user');
        const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(newUserEmail));
        await expect(activateButton).toBeVisible({ timeout: 5000 });
        await activateButton.click();

        const confirmButton = page.getByRole('button', { name: 'general.yes' });
        await expect(confirmButton).toBeVisible();
        await confirmButton.click();

        const deactivateButton = page.getByTestId(UserPageIDs.systemUserDeactivateButton(newUserEmail));
        await expect(deactivateButton).toBeVisible({ timeout: 5000 });

        testDataManager.updateCreatedUserActivation(newUserEmail, true);
        await testReporter.completeStep('Activate user', 'passed');
        await testReporter.finalizeTest();
    });

    test('should deactivate user @system @users @permissions @regression', async ({
        page,
        testReporter
    }) => {
        const tempUser = testDataManager.getUser('tempuser');
        const newUserEmail = tempUser.email;

        const stepNavigate = await testReporter.startStep('Navigate to Users section');
        await page.getByTestId(UserPageIDs.mainNavOrganization).click();
        await page.getByTestId(UserPageIDs.mainNavOrganizationUsers).click();
        const userTable = page.getByTestId(UserPageIDs.systemUserTable);
        await expect(userTable).toBeVisible({ timeout: 10000 });
        await testReporter.completeStep('Navigate to Users section', 'passed');

        const stepDeactivateUser = await testReporter.startStep('Deactivate user');
        const deactivateButton = page.getByTestId(UserPageIDs.systemUserDeactivateButton(newUserEmail));
        await expect(deactivateButton).toBeVisible({ timeout: 5000 });
        await deactivateButton.click();

        const confirmDeactivateButton = page.getByRole('button', { name: 'general.yes' });
        await expect(confirmDeactivateButton).toBeVisible();
        await confirmDeactivateButton.click();

        const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(newUserEmail));
        await expect(activateButton).toBeVisible({ timeout: 5000 });

        testDataManager.updateCreatedUserActivation(newUserEmail, false);
        await testReporter.completeStep('Deactivate user', 'passed');
        await testReporter.finalizeTest();
    });
});
