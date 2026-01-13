import type { Page } from '@playwright/test';
import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { TestDataManager } from '../../src/utils/data/TestDataManager';
import { ensureCreatedUser } from '../helpers/user-helpers';

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

  const ensureUserActive = async (page: Page, email: string): Promise<void> => {
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    const searchInput = page.getByTestId('resource-list-search');
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill(email);
      await searchInput.press('Enter');
    }

    const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(email));
    if (await activateButton.isVisible().catch(() => false)) {
      await activateButton.click();
      const confirm = page.getByRole('button', { name: /yes/i });
      await expect(confirm).toBeVisible();
      await confirm.click();
    }
  };

  test('should add created user to team @system @users @teams @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    const createdUser = await ensureCreatedUser(page, testDataManager);

    const userEmail = createdUser.email;
    const teamName = 'Private Team';

    await ensureUserActive(page, userEmail);

    testReporter.startStep('Navigate to Teams section');

    // Navigate to Organization > Teams
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationTeams();

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
    await userCombobox.fill(userEmail);

    // Select the user from dropdown
    const dropdown = page.locator('.ant-select-dropdown').filter({ hasText: userEmail });
    await expect(dropdown).toBeVisible({ timeout: 5000 });
    const userOption = dropdown
      .locator('.ant-select-item-option')
      .filter({ hasText: userEmail })
      .first();
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

    // Refresh modal to ensure latest members are loaded
    await page.getByRole('button', { name: 'Close' }).click();
    await expect(teamMembersButton).toBeVisible({ timeout: 5000 });
    await teamMembersButton.click();
    await expect(teamModal).toBeVisible({ timeout: 5000 });

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
    const userToAdd = await ensureCreatedUser(page, testDataManager);
    const teamName = 'Private Team';

    await ensureUserActive(page, userToAdd.email);

    testReporter.startStep('Navigate to Teams section');

    const nav = new NavigationHelper(page);
    await nav.goToOrganizationTeams();

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

    await userCombobox.fill(userToAdd.email);
    const dropdown = page.locator('.ant-select-dropdown').filter({ hasText: userToAdd.email });
    await expect(dropdown).toBeVisible({ timeout: 5000 });
    const userOption = dropdown
      .locator('.ant-select-item-option')
      .filter({ hasText: userToAdd.email })
      .first();
    await expect(userOption).toBeVisible({ timeout: 5000 });
    await userOption.click();

    const addButton = page.getByRole('button', { name: 'Add Member' });
    await expect(addButton).toBeVisible();
    await addButton.click();

    // Wait for API response to complete
    await page.waitForLoadState('networkidle');

    testReporter.completeStep(`Add user ${userToAdd.email} to team`, 'passed');

    testReporter.startStep('Verify user in team members');

    await page.getByRole('button', { name: 'Close' }).click();
    await expect(teamMembersButton).toBeVisible({ timeout: 5000 });
    await teamMembersButton.click();
    await expect(teamModal).toBeVisible({ timeout: 5000 });

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
