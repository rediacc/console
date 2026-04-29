import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';
import { UserPageIDs } from '@/pages/user/UserPageIDs';
import {
  selectUserInAddMemberTab,
  openTeamMembersDialog,
  dismissCreateUserModal,
  waitForTeamsPage,
  fillResourceSearch,
} from '@/test-helpers/team-helpers';
import { createUserViaUI } from '@/test-helpers/user-helpers';
import { confirmYes } from '@/test-helpers/ui-helpers';
import type { Page } from '@playwright/test';

const ensureUserActive = async (page: Page, email: string): Promise<void> => {
  const nav = new NavigationHelper(page);
  await nav.goToOrganizationUsers();

  await fillResourceSearch(page, email);

  const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(email));
  if (await activateButton.isVisible().catch(() => false)) {
    await activateButton.click();
    await confirmYes(page);
  }
};

test.describe('Team Members - Add Created User Tests', () => {
  test.describe.configure({ timeout: 60000 });
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should add created user to team @system @users @teams @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
    testDataManager,
  }) => {
    const createdUser = await createUserViaUI(page, testDataManager);
    await dismissCreateUserModal(page);

    const userEmail = createdUser.email;
    const teamName = 'Private Team';

    await ensureUserActive(page, userEmail);

    testReporter.startStep('Navigate to Teams section');

    // Navigate to Organization > Teams
    await dismissCreateUserModal(page);
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationTeams();
    await waitForTeamsPage(page);
    await fillResourceSearch(page, teamName);

    testReporter.completeStep('Navigate to Teams section', 'passed');

    testReporter.startStep('Open team members dialog');

    // Open team members dialog
    await openTeamMembersDialog(page, teamName);

    // Wait for modal to open
    const teamModal = page.locator('.ant-modal').filter({ hasText: 'Manage Team Members' });
    await expect(teamModal).toBeVisible({ timeout: 5000 });

    testReporter.completeStep('Open team members dialog', 'passed');

    testReporter.startStep('Add user to team');

    // Switch to Add Member tab
    const addMemberTab = page.getByRole('tab', { name: 'Add Member' });
    await expect(addMemberTab).toBeVisible();
    await addMemberTab.click();

    await selectUserInAddMemberTab(page, userEmail);

    // Wait for API response to complete
    await page.waitForLoadState('networkidle');

    testReporter.completeStep('Add user to team', 'passed');

    testReporter.startStep('Verify user in team members');

    await expect(teamModal).toBeVisible({ timeout: 5000 });

    // Switch to Current Members tab
    const currentMembersTab = page.getByRole('tab', { name: 'Current Members' });
    await expect(currentMembersTab).toBeVisible();
    await currentMembersTab.click();

    // Verify user appears in members list
    const membersList = teamModal.locator('.ant-list-items');
    await expect(membersList).toBeVisible();

    const userInList = membersList
      .locator('.ant-list-item-meta-title')
      .filter({ hasText: userEmail });
    await expect(userInList).toBeVisible({ timeout: 5000 });

    testReporter.completeStep('Verify user in team members', 'passed');

    await testReporter.finalizeTest();
  });
});
