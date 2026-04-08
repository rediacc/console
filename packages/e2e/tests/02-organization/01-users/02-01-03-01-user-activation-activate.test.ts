import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';
import { UserPageIDs } from '@/pages/user/UserPageIDs';
import { createUserViaUI } from '@/test-helpers/user-helpers';
import {
  waitForNoModal,
  filterUsersList,
  clickListAction,
  confirmYes,
} from '@/test-helpers/ui-helpers';

test.describe('User Permission Tests - Activate', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should activate user @system @users @permissions @regression', async ({
    page,
    testReporter,
    testDataManager,
  }) => {
    const createdUser = await createUserViaUI(page, testDataManager);
    const newUserEmail = createdUser.email;

    testReporter.startStep('Navigate to Users section');

    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    const userTable = page.getByTestId(UserPageIDs.systemUserTable);
    const listContainer = page.getByTestId('resource-list-container');
    await expect(userTable.or(listContainer)).toBeVisible({ timeout: 10000 });
    await filterUsersList(page, newUserEmail);
    testReporter.completeStep('Navigate to Users section', 'passed');

    testReporter.startStep('Activate user');
    const isTableLayout = await userTable.isVisible().catch(() => false);
    if (isTableLayout) {
      const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(newUserEmail));
      const deactivateButton = page.getByTestId(
        UserPageIDs.systemUserDeactivateButton(newUserEmail)
      );
      if (await deactivateButton.isVisible().catch(() => false)) {
        await waitForNoModal(page);
        await deactivateButton.click();
        await confirmYes(page);
      }
      await expect(activateButton).toBeVisible({ timeout: 5000 });
      await waitForNoModal(page);
      await activateButton.click();
      await confirmYes(page);
      await expect(deactivateButton).toBeVisible({ timeout: 5000 });
    } else {
      const listItem = page.getByTestId(UserPageIDs.resourceListItem(newUserEmail));
      await expect(listItem).toBeVisible({ timeout: 5000 });
      const activeTag = listItem.getByText('Active', { exact: true });
      const inactiveTag = listItem.getByText('Inactive', { exact: true });
      if (await activeTag.isVisible().catch(() => false)) {
        await clickListAction(page, newUserEmail, 'deactivate');
        await expect(inactiveTag).toBeVisible({ timeout: 10000 });
      }
      await clickListAction(page, newUserEmail, 'activate');
      await expect(activeTag).toBeVisible({ timeout: 10000 });
    }

    await testDataManager.updateCreatedUserActivation(newUserEmail, true);
    testReporter.completeStep('Activate user', 'passed');
    await testReporter.finalizeTest();
  });
});
