import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { ensureCreatedUser } from '../helpers/user-helpers';

test.describe('User Permission Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should assign permissions to user @system @organization @permission @regression', async ({
    page,
    testReporter,
    testDataManager,
  }) => {
    test.setTimeout(60000);
    testReporter.startStep('Navigate to Organization Users section');

    const createdUser = await ensureCreatedUser(page, testDataManager);

    // Navigate to Organization > Users
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    const verifyUserVisible = async (): Promise<boolean> => {
      await nav.goToOrganizationUsers();
      const searchInput = page.getByTestId('resource-list-search');
      if (await searchInput.isVisible().catch(() => false)) {
        await searchInput.fill('');
        await searchInput.fill(createdUser.email);
        await searchInput.press('Enter');
      }
      const listItem = page.getByTestId(UserPageIDs.resourceListItem(createdUser.email));
      if (await listItem.isVisible().catch(() => false)) {
        return true;
      }
      const userTable = page.getByTestId(UserPageIDs.systemUserTable);
      return await userTable
        .getByText(createdUser.email, { exact: true })
        .isVisible()
        .catch(() => false);
    };

    await expect.poll(async () => verifyUserVisible(), { timeout: 15000 }).toBe(true);

    testReporter.completeStep('Navigate to Organization Users section', 'passed');

    testReporter.startStep('Assign permissions to user');

    // Open permission modal
    const searchInput = page.getByTestId('resource-list-search');
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill('');
      await searchInput.fill(createdUser.email);
      await searchInput.press('Enter');
    }

    const userRow = page.getByTestId(UserPageIDs.resourceListItem(createdUser.email));
    await expect(userRow).toBeVisible({ timeout: 5000 });

    const permissionsButton = page.getByTestId(
      UserPageIDs.systemUserPermissionsButton(createdUser.email)
    );
    if (await permissionsButton.isVisible().catch(() => false)) {
      await expect(permissionsButton).toBeVisible({ timeout: 5000 });
      await expect(permissionsButton).toBeEnabled();
      await permissionsButton.scrollIntoViewIfNeeded();
      await permissionsButton.click({ force: true });
    } else {
      const listItem = page.getByTestId(UserPageIDs.resourceListItem(createdUser.email));
      await expect(listItem).toBeVisible({ timeout: 5000 });
      const actionsButton = listItem.getByRole('button', { name: /actions/i });
      await expect(actionsButton).toBeVisible();
      await actionsButton.click();
      const permissionsMenuItem = page.getByRole('menuitem', { name: /permissions/i });
      await expect(permissionsMenuItem).toBeVisible({ timeout: 5000 });
      await permissionsMenuItem.click();
    }

    const assignDialog = page.getByRole('dialog', { name: /Assign Permissions/i });
    await expect(assignDialog).toBeVisible({ timeout: 10000 });

    const permissionSelect = assignDialog.getByTestId('user-permission-group-select');
    await expect(permissionSelect).toBeVisible();
    await permissionSelect.click();

    const dropdown = page.locator('.ant-select-dropdown');
    await expect(dropdown).toBeVisible({ timeout: 5000 });
    const usersOption = dropdown.locator('.ant-select-item-option').filter({ hasText: /Users/i });
    await expect(usersOption.first()).toBeVisible({ timeout: 5000 });
    await usersOption.first().click();
    await expect(dropdown).toBeHidden({ timeout: 5000 });

    // Confirm
    await expect(assignDialog).toBeVisible();
    await assignDialog.getByTestId(UserPageIDs.modalAssignPermissionsOk).click();

    testReporter.completeStep('Assign permissions to user', 'passed');
    await testReporter.finalizeTest();
  });
});
