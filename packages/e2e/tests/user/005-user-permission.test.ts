import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

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

  test('should assign permissions to user @system @organization @permission @regression', async ({
    page,
    testReporter,
  }) => {
    testReporter.startStep('Navigate to Organization Users section');

    // Get created user
    const createdUser = testDataManager.getCreatedUser();

    // organization
    await page.getByTestId(UserPageIDs.mainNavOrganization).click();

    // user table
    await page.getByTestId(UserPageIDs.subNavOrganizationUsers).click();
    await expect(page.getByRole('cell', { name: `user ${createdUser.email}` })).toBeVisible();

    testReporter.completeStep('Navigate to Organization Users section', 'passed');

    testReporter.startStep('Assign permissions to user');

    // Open permission modal
    await page.getByTestId(UserPageIDs.systemUserPermissionsButton(createdUser.email)).click();

    // Select permission (using "Users" as a partial match)
    await page.getByTitle(/Users/).click();

    // Confirm
    await page.getByTestId(UserPageIDs.modalAssignPermissionsOk).click();

    testReporter.completeStep('Assign permissions to user', 'passed');
    await testReporter.finalizeTest();
  });
});
