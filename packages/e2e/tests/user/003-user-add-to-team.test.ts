import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { waitForTeamRow } from '../helpers/team-helpers';
import { createUserViaUI } from '../helpers/user-helpers';
import type { Page } from '@playwright/test';

test.describe('User Team Assignment Tests', () => {
  test.describe.configure({ timeout: 60000 });
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  const selectUserInAddMemberTab = async (page: Page, email: string): Promise<void> => {
    const addMemberPanel = page.getByRole('tabpanel', { name: 'Add Member' });
    const userCombobox = addMemberPanel.getByRole('combobox');
    await expect(userCombobox).toBeVisible();
    await userCombobox.click();
    await userCombobox.fill(email);
    await userCombobox.press('Enter');

    const addButton = addMemberPanel.getByRole('button', { name: 'Add Member' });
    await expect(addButton).toBeVisible();
    try {
      await expect(addButton).toBeEnabled({ timeout: 5000 });
    } catch {
      await userCombobox.click();
      await userCombobox.press('ArrowDown');
      const userOption = page.getByRole('option', { name: email });
      await expect(userOption).toBeAttached({ timeout: 10000 });
      await userOption.click({ force: true });
      await expect(addButton).toBeEnabled({ timeout: 10000 });
    }
    await addButton.click();
  };
  const openTeamMembersDialog = async (page: Page, teamName: string): Promise<void> => {
    const dismissDrawerMask = async (): Promise<void> => {
      const mask = page.locator('.ant-drawer-mask');
      if (await mask.isVisible().catch(() => false)) {
        try {
          await mask.click({ force: true });
          await mask.waitFor({ state: 'hidden', timeout: 3000 });
        } catch {
          await page.keyboard.press('Escape').catch(() => null);
          await page.evaluate(() => {
            const overlay = document.querySelector<HTMLElement>('.ant-drawer-mask');
            if (overlay) {
              overlay.style.pointerEvents = 'none';
              overlay.style.opacity = '0';
            }
          });
        }
      }
    };
    const teamMembersButton = page.getByTestId(UserPageIDs.systemTeamMembersButton(teamName));
    if (await teamMembersButton.isVisible().catch(() => false)) {
      await dismissDrawerMask();
      await teamMembersButton.click();
      return;
    }

    const teamRow = await waitForTeamRow(page, teamName);
    const rowMembersButton = teamRow.getByRole('button', { name: /members/i });
    try {
      await expect(rowMembersButton).toBeVisible({ timeout: 3000 });
      await rowMembersButton.first().click();
      return;
    } catch {
      // Fall through to other strategies.
    }

    const genericMembersButton = page.getByRole('button', { name: /^members$/i });
    try {
      await expect(genericMembersButton).toBeVisible({ timeout: 3000 });
      await genericMembersButton.first().click();
      return;
    } catch {
      // Fall through to list actions.
    }

    const actionsButton = teamRow.getByRole('button', { name: /actions/i });
    await expect(actionsButton).toBeVisible();
    await dismissDrawerMask();
    await actionsButton.click();
    const membersMenuItem = page.getByRole('menuitem', { name: /members/i });
    await expect(membersMenuItem).toBeVisible();
    await membersMenuItem.click();
  };
  const dismissCreateUserModal = async (page: Page): Promise<void> => {
    const createModal = page.getByTestId('users-create-modal');
    const createDialog = page.getByRole('dialog', { name: /create user/i });
    if (
      (await createModal.isVisible().catch(() => false)) ||
      (await createDialog.isVisible().catch(() => false))
    ) {
      const closeButton = createDialog.getByRole('button', { name: /cancel|close/i }).first();
      if (await closeButton.isVisible().catch(() => false)) {
        try {
          await closeButton.click();
        } catch {
          await page.keyboard.press('Escape').catch(() => null);
        }
      } else {
        await page.keyboard.press('Escape').catch(() => null);
      }
      await expect(createModal)
        .toBeHidden({ timeout: 10000 })
        .catch(() => null);
      await expect(createDialog)
        .toBeHidden({ timeout: 10000 })
        .catch(() => null);
    }
  };
  const waitForTeamsPage = async (page: Page): Promise<void> => {
    const createButton = page.getByTestId('system-create-team-button');
    const listContainer = page.getByTestId('resource-list-container');
    await expect
      .poll(
        async () =>
          (await createButton.isVisible().catch(() => false)) ||
          (await listContainer.isVisible().catch(() => false)),
        { timeout: 10000 }
      )
      .toBe(true);
  };
  const fillResourceSearch = async (page: Page, value: string): Promise<void> => {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const searchInput = page.getByTestId('resource-list-search');
      if (!(await searchInput.isVisible().catch(() => false))) {
        return;
      }
      try {
        await expect(searchInput).toBeVisible({ timeout: 3000 });
        await expect(searchInput).toBeEditable({ timeout: 3000 });
        await searchInput.fill(value);
        await searchInput.press('Enter');
        return;
      } catch (error) {
        if (attempt === 2) {
          throw error;
        }
      }
    }
  };

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

  test('should add specific user to team by email @system @users @teams', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
    testDataManager,
  }) => {
    const userToAdd = await createUserViaUI(page, testDataManager);
    await dismissCreateUserModal(page);
    const teamName = 'Private Team';

    await ensureUserActive(page, userToAdd.email);

    testReporter.startStep('Navigate to Teams section');

    await dismissCreateUserModal(page);
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

    // Wait for API response to complete
    await page.waitForLoadState('networkidle');

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
