import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { createUserViaUI } from '../helpers/user-helpers';

test.describe('User Creation Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should create new user @system @users @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
    testDataManager,
  }) => {
    test.setTimeout(60000);
    testReporter.startStep('Navigate to Users section');

    // Navigate to Organization > Users
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    const userTable = page.getByTestId(UserPageIDs.systemUserTable);
    const listContainer = page.getByTestId('resource-list-container');
    await expect
      .poll(
        async () =>
          (await userTable.isVisible().catch(() => false)) ||
          (await listContainer.isVisible().catch(() => false)),
        { timeout: 10000 }
      )
      .toBe(true);

    testReporter.completeStep('Navigate to Users section', 'passed');

    testReporter.startStep('Create new user');

    await createUserViaUI(page, testDataManager);

    testReporter.completeStep('Create new user', 'passed');

    await testReporter.finalizeTest();
  });
});
