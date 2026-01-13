import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { createUserViaUI } from '../helpers/user-helpers';

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
    testReporter,
  }) => {
    const createdUser = await createUserViaUI(page, testDataManager);
    const newUserEmail = createdUser.email;

    testReporter.startStep('Navigate to Users section');

    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    const userTable = page.getByTestId(UserPageIDs.systemUserTable);
    await expect(userTable).toBeVisible({ timeout: 10000 });
    testReporter.completeStep('Navigate to Users section', 'passed');

    testReporter.startStep('Activate user');
    const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(newUserEmail));
    if (!(await activateButton.isVisible().catch(() => false))) {
      const deactivateButton = page.getByTestId(
        UserPageIDs.systemUserDeactivateButton(newUserEmail)
      );
      if (await deactivateButton.isVisible().catch(() => false)) {
        await deactivateButton.click();
        const confirmDeactivate = page.getByRole('button', { name: /yes/i });
        await expect(confirmDeactivate).toBeVisible();
        await confirmDeactivate.click();
      }
    }
    await expect(activateButton).toBeVisible({ timeout: 5000 });
    await activateButton.click();

    const confirmButton = page.getByRole('button', { name: /yes/i });
    await expect(confirmButton).toBeVisible();
    await confirmButton.click();

    const deactivateButton = page.getByTestId(UserPageIDs.systemUserDeactivateButton(newUserEmail));
    await expect(deactivateButton).toBeVisible({ timeout: 5000 });

    testDataManager.updateCreatedUserActivation(newUserEmail, true);
    testReporter.completeStep('Activate user', 'passed');
    await testReporter.finalizeTest();
  });

  test('should deactivate user @system @users @permissions @regression', async ({
    page,
    testReporter,
  }) => {
    const createdUser = await createUserViaUI(page, testDataManager);
    const newUserEmail = createdUser.email;

    testReporter.startStep('Navigate to Users section');

    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    const userTable = page.getByTestId(UserPageIDs.systemUserTable);
    await expect(userTable).toBeVisible({ timeout: 10000 });
    testReporter.completeStep('Navigate to Users section', 'passed');

    testReporter.startStep('Deactivate user');
    const deactivateButton = page.getByTestId(UserPageIDs.systemUserDeactivateButton(newUserEmail));
    if (!(await deactivateButton.isVisible().catch(() => false))) {
      const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(newUserEmail));
      await expect(activateButton).toBeVisible({ timeout: 5000 });
      await activateButton.click();
      const confirmActivate = page.getByRole('button', { name: /yes/i });
      await expect(confirmActivate).toBeVisible();
      await confirmActivate.click();
    }
    await expect(deactivateButton).toBeVisible({ timeout: 5000 });
    await deactivateButton.click();

    const confirmDeactivateButton = page.getByRole('button', { name: /yes/i });
    await expect(confirmDeactivateButton).toBeVisible();
    await confirmDeactivateButton.click();

    const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(newUserEmail));
    await expect(activateButton).toBeVisible({ timeout: 5000 });

    testDataManager.updateCreatedUserActivation(newUserEmail, false);
    testReporter.completeStep('Deactivate user', 'passed');
    await testReporter.finalizeTest();
  });
});
