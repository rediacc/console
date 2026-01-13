import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

// Skip: TestDataManager requires VM_WORKER_IPS which is not set in CI
test.describe
  .skip('User Permission Tests', () => {
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
      const tempUser = testDataManager.getUser('tempuser');
      const newUserEmail = tempUser.email;

      testReporter.startStep('Navigate to Users section');
      await page.getByTestId(UserPageIDs.mainNavOrganization).click();
      await page.getByTestId(UserPageIDs.subNavOrganizationUsers).click();
      const userTable = page.getByTestId(UserPageIDs.systemUserTable);
      await expect(userTable).toBeVisible({ timeout: 10000 });
      testReporter.completeStep('Navigate to Users section', 'passed');

      testReporter.startStep('Activate user');
      const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(newUserEmail));
      await expect(activateButton).toBeVisible({ timeout: 5000 });
      await activateButton.click();

      const confirmButton = page.getByRole('button', { name: 'general.yes' });
      await expect(confirmButton).toBeVisible();
      await confirmButton.click();

      const deactivateButton = page.getByTestId(
        UserPageIDs.systemUserDeactivateButton(newUserEmail)
      );
      await expect(deactivateButton).toBeVisible({ timeout: 5000 });

      testDataManager.updateCreatedUserActivation(newUserEmail, true);
      testReporter.completeStep('Activate user', 'passed');
      await testReporter.finalizeTest();
    });

    test('should deactivate user @system @users @permissions @regression', async ({
      page,
      testReporter,
    }) => {
      const tempUser = testDataManager.getUser('tempuser');
      const newUserEmail = tempUser.email;

      testReporter.startStep('Navigate to Users section');
      await page.getByTestId(UserPageIDs.mainNavOrganization).click();
      await page.getByTestId(UserPageIDs.subNavOrganizationUsers).click();
      const userTable = page.getByTestId(UserPageIDs.systemUserTable);
      await expect(userTable).toBeVisible({ timeout: 10000 });
      testReporter.completeStep('Navigate to Users section', 'passed');

      testReporter.startStep('Deactivate user');
      const deactivateButton = page.getByTestId(
        UserPageIDs.systemUserDeactivateButton(newUserEmail)
      );
      await expect(deactivateButton).toBeVisible({ timeout: 5000 });
      await deactivateButton.click();

      const confirmDeactivateButton = page.getByRole('button', { name: 'general.yes' });
      await expect(confirmDeactivateButton).toBeVisible();
      await confirmDeactivateButton.click();

      const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(newUserEmail));
      await expect(activateButton).toBeVisible({ timeout: 5000 });

      testDataManager.updateCreatedUserActivation(newUserEmail, false);
      testReporter.completeStep('Deactivate user', 'passed');
      await testReporter.finalizeTest();
    });
  });
