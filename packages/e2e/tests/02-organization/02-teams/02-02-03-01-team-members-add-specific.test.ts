import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';
import { UserPageIDs } from '@/pages/user/UserPageIDs';
import {
  selectUserInAddMemberTab,
  openTeamMembersDialog,
  waitForTeamsPage,
  fillResourceSearch,
} from '@/test-helpers/team-helpers';
import { createUserViaUI } from '@/test-helpers/user-helpers';
import type { Page } from '@playwright/test';

test.describe('User Team Assignment Tests - Add Specific User', () => {
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

  const ensureUserActive = async (page: Page, email: string): Promise<void> => {
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    await fillResourceSearch(page, email);

    const activateButton = page.getByTestId(UserPageIDs.systemUserActivateButton(email));
    if (await activateButton.isVisible().catch(() => false)) {
      await activateButton.click();
      const confirm = page.getByRole('button', { name: /yes/i });
      await expect(confirm).toBeVisible();
      await confirm.click();
    }
  };

  test('should add specific user to team by email @system @users @teams', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
    testDataManager,
  }) => {
    const userToAdd = await createUserViaUI(page, testDataManager);
    const teamName = 'Private Team';

    await ensureUserActive(page, userToAdd.email);

    testReporter.startStep('Navigate to Teams section');

    const nav = new NavigationHelper(page);
    await nav.goToOrganizationTeams();
    await waitForTeamsPage(page);
    await fillResourceSearch(page, teamName);

    testReporter.completeStep('Navigate to Teams section', 'passed');

    testReporter.startStep(`Add user ${userToAdd.email} to team`);

    await openTeamMembersDialog(page, teamName);

    const teamModal = page.locator('.ant-modal').filter({ hasText: 'Manage Team Members' });
    await expect(teamModal).toBeVisible({ timeout: 5000 });

    const addMemberTab = page.getByRole('tab', { name: 'Add Member' });
    await expect(addMemberTab).toBeVisible();
    await addMemberTab.click();

    await selectUserInAddMemberTab(page, userToAdd.email);

    testReporter.completeStep(`Add user ${userToAdd.email} to team`, 'passed');

    testReporter.startStep('Verify user in team members');

    await expect(teamModal).toBeVisible({ timeout: 5000 });

    const currentMembersTab = page.getByRole('tab', { name: 'Current Members' });
    await expect(currentMembersTab).toBeVisible();
    await currentMembersTab.click();

    const membersList = teamModal.locator('.ant-list-items');
    await expect(membersList).toBeVisible();

    const userInList = membersList
      .locator('.ant-list-item-meta-title')
      .filter({ hasText: userToAdd.email });
    await expect(userInList).toBeVisible({ timeout: 5000 });

    testReporter.completeStep('Verify user in team members', 'passed');

    await testReporter.finalizeTest();
  });
});
