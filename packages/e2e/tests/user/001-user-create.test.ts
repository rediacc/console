import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { createUserViaUI } from '../helpers/user-helpers';

test.describe('User Creation Tests', () => {
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

  test('should create new user @system @users @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    testReporter.startStep('Navigate to Users section');

    // Navigate to Organization > Users
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    // Wait for user table to be visible
    const userTable = page.getByTestId(UserPageIDs.systemUserTable);
    await expect(userTable).toBeVisible({ timeout: 10000 });

    testReporter.completeStep('Navigate to Users section', 'passed');

    testReporter.startStep('Create new user');

    await createUserViaUI(page, testDataManager);

    testReporter.completeStep('Create new user', 'passed');

    await testReporter.finalizeTest();
  });
});
