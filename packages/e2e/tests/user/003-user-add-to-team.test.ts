import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { TestDataManager } from '../../src/utils/data/TestDataManager';

test.describe('User Team Assignment Tests', () => {
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

  test('should add created user to team @system @users @teams @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    // Get the most recently created user from test data
    let createdUser;
    try {
      createdUser = testDataManager.getCreatedUser();
    } catch {
      throw new Error(
        'No created user found. Please run user-create.test.ts first to create a user.'
      );
    }

    const userEmail = createdUser.email;
    const teamName = 'Private Team';

    testReporter.startStep('Navigate to Teams section');

    // Navigate to Organization > Teams
    await page.getByTestId(UserPageIDs.mainNavOrganization).click();
    await page.getByTestId(UserPageIDs.mainNavOrganizationTeams).click();

    testReporter.completeStep('Navigate to Teams section', 'passed');

    testReporter.startStep('Open team members dialog');

    // Open team members dialog
    const teamMembersButton = page.getByTestId(UserPageIDs.systemTeamMembersButton(teamName));
    await expect(teamMembersButton).toBeVisible({ timeout: 5000 });
    await teamMembersButton.click();

    // Wait for modal to open
    const teamModal = page.locator('.ant-modal').filter({ hasText: 'Manage Team Members' });
    await expect(teamModal).toBeVisible({ timeout: 5000 });

    testReporter.completeStep('Open team members dialog', 'passed');

    testReporter.startStep('Add user to team');

    // Switch to Add Member tab
    const addMemberTab = page.getByRole('tab', { name: 'Add Member' });
    await expect(addMemberTab).toBeVisible();
    await addMemberTab.click();

    // Click on the combobox in Add Member tab panel
    const addMemberPanel = page.getByRole('tabpanel', { name: 'Add Member' });
    const userCombobox = addMemberPanel.getByRole('combobox');
    await expect(userCombobox).toBeVisible();
    await userCombobox.click();

    // Select the user from dropdown
    const userOption = page.getByText(userEmail).nth(1);
    await expect(userOption).toBeVisible({ timeout: 5000 });
    await userOption.click();

    // Click the plus button to add the member
    const addButton = page.getByRole('button', { name: 'Add Member' });
    await expect(addButton).toBeVisible();
    await addButton.click();

    // Wait for API response to complete
    await page.waitForLoadState('networkidle');

    testReporter.completeStep('Add user to team', 'passed');

    testReporter.startStep('Verify user in team members');

    // Switch to Current Members tab
    const currentMembersTab = page.getByRole('tab', { name: 'Current Members' });
    await expect(currentMembersTab).toBeVisible();
    await currentMembersTab.click();

    // Verify user appears in members list
    const membersList = page.locator('.ant-list-items');
    await expect(membersList).toBeVisible();

    const userInList = membersList
      .locator('.ant-list-item-meta-title')
      .filter({ hasText: userEmail });
    await expect(userInList).toBeVisible({ timeout: 5000 });

    testReporter.completeStep('Verify user in team members', 'passed');

    await testReporter.finalizeTest();
  });

  test('should add specific user to team by email @system @users @teams', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    // List all created users for reference
    const allCreatedUsers = testDataManager.getAllCreatedUsers();

    if (allCreatedUsers.length === 0) {
      throw new Error('No created users found. Please run user-create.test.ts first.');
    }

    console.warn(`Available created users (${allCreatedUsers.length}):`);
    for (const [index, user] of allCreatedUsers.entries()) {
      console.warn(
        `  ${index + 1}. ${user.email} (activated: ${user.activated}, created: ${user.createdAt})`
      );
    }

    // You can specify which user to add by getting a specific one
    // For example: const userToAdd = testDataManager.getCreatedUser('specific@email.com');
    const userToAdd = allCreatedUsers[0]; // Use the first created user
    const teamName = 'Private Team';

    testReporter.startStep('Navigate to Teams section');

    await page.getByTestId(UserPageIDs.mainNavOrganization).click();
    await page.getByTestId(UserPageIDs.mainNavOrganizationTeams).click();

    testReporter.completeStep('Navigate to Teams section', 'passed');

    testReporter.startStep(`Add user ${userToAdd.email} to team`);

    const teamMembersButton = page.getByTestId(UserPageIDs.systemTeamMembersButton(teamName));
    await expect(teamMembersButton).toBeVisible({ timeout: 5000 });
    await teamMembersButton.click();

    const teamModal = page.locator('.ant-modal').filter({ hasText: 'Manage Team Members' });
    await expect(teamModal).toBeVisible({ timeout: 5000 });

    const addMemberTab = page.getByRole('tab', { name: 'Add Member' });
    await expect(addMemberTab).toBeVisible();
    await addMemberTab.click();

    const addMemberPanel = page.getByRole('tabpanel', { name: 'Add Member' });
    const userCombobox = addMemberPanel.getByRole('combobox');
    await expect(userCombobox).toBeVisible();
    await userCombobox.click();

    const userOption = page.getByText(userToAdd.email).nth(1);
    await expect(userOption).toBeVisible({ timeout: 5000 });
    await userOption.click();

    const addButton = page.getByRole('button', { name: 'Add Member' });
    await expect(addButton).toBeVisible();
    await addButton.click();

    // Wait for API response to complete
    await page.waitForLoadState('networkidle');

    testReporter.completeStep(`Add user ${userToAdd.email} to team`, 'passed');

    testReporter.startStep('Verify user in team members');

    const currentMembersTab = page.getByRole('tab', { name: 'Current Members' });
    await expect(currentMembersTab).toBeVisible();
    await currentMembersTab.click();

    const membersList = page.locator('.ant-list-items');
    await expect(membersList).toBeVisible();

    const userInList = membersList
      .locator('.ant-list-item-meta-title')
      .filter({ hasText: userToAdd.email });
    await expect(userInList).toBeVisible({ timeout: 5000 });

    testReporter.completeStep('Verify user in team members', 'passed');

    await testReporter.finalizeTest();
  });
});
