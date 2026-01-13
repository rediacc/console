import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

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
    // Generate unique user email
    const tempUser = testDataManager.getUser('tempuser');
    const newUserEmail = tempUser.email;
    const newUserPassword = tempUser.password;

    testReporter.startStep('Navigate to Users section');

    // Navigate to Organization > Users
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    // Wait for user table to be visible
    const userTable = page.getByTestId(UserPageIDs.systemUserTable);
    await expect(userTable).toBeVisible({ timeout: 10000 });

    testReporter.completeStep('Navigate to Users section', 'passed');

    testReporter.startStep('Create new user');

    // Click create user button
    const createUserButton = page.getByTestId(UserPageIDs.systemCreateUserButton);
    await expect(createUserButton).toBeVisible({ timeout: 5000 });
    await createUserButton.click();

    // Fill user form
    const emailField = page.getByTestId(UserPageIDs.resourceFormFieldEmail);
    const passwordField = page.getByTestId(UserPageIDs.resourceFormFieldPassword);

    await expect(emailField).toBeVisible();
    await expect(passwordField).toBeVisible();

    await emailField.fill(newUserEmail);
    await passwordField.fill(newUserPassword);

    // Submit form
    const submitButton = page.getByTestId(UserPageIDs.resourceFormSubmitButton);
    await expect(submitButton).toBeVisible();
    await submitButton.click();

    // Verify user created message
    await expect(page.getByText(`User "${newUserEmail}"`)).toBeVisible({ timeout: 5000 });

    // Save user to test data
    testDataManager.addCreatedUser(newUserEmail, newUserPassword, false);

    testReporter.completeStep('Create new user', 'passed');

    await testReporter.finalizeTest();
  });
});
