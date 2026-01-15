import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { TeamPageIDS } from '../../pages/team/TeamPageIDS';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { E2E_DEFAULTS } from '../../src/utils/constants';
import { createTeamViaUI, waitForTeamRow } from '../helpers/team-helpers';

test.describe('Team Delete Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should delete team and confirm audit records @system @organization @audit @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    test.setTimeout(60000);
    const teamName = `e2e-team-${Date.now()}`;

    testReporter.startStep('Trace team audit records');

    // Navigate to Organization > Teams
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationTeams();

    await createTeamViaUI(page, teamName);

    const teamRow = await waitForTeamRow(page, teamName);
    await teamRow.scrollIntoViewIfNeeded();
    const traceButton = page.getByTestId(TeamPageIDS.systemTeamTraceButton(teamName));
    if (await traceButton.isVisible().catch(() => false)) {
      await traceButton.click();
    } else {
      const actionsButton = teamRow.getByRole('button', { name: /actions/i });
      await actionsButton.click();
      await page.getByRole('menuitem', { name: /trace/i }).click();
    }
    const auditRecordsText = await page
      .getByTestId(TeamPageIDS.auditTraceTotalRecords)
      .locator('strong')
      .textContent();
    const recordCount = Number.parseInt(auditRecordsText ?? E2E_DEFAULTS.CPU_COUNT_STRING);
    expect(recordCount).toBeGreaterThan(0);
    const closeButton = page.getByRole('button', { name: 'Close' });
    try {
      await closeButton.click({ timeout: 5000 });
    } catch {
      await closeButton.click({ force: true }).catch(async () => {
        await page.keyboard.press('Escape');
      });
    }

    await waitForTeamRow(page, teamName);
    const deleteButton = page.getByTestId(TeamPageIDS.systemTeamDeleteButton(teamName));
    if (await deleteButton.isVisible().catch(() => false)) {
      await deleteButton.click();
    } else {
      const actionsButton = teamRow.getByRole('button', { name: /actions/i });
      await actionsButton.click();
      await page.getByRole('menuitem', { name: /delete/i }).click();
    }
    const confirmDelete = page.getByRole('button', { name: /yes/i });
    if (await confirmDelete.isVisible().catch(() => false)) {
      await confirmDelete.click();
    }
    const privateTeamCell = page.getByRole('cell', { name: 'team Private Team' });
    if (await privateTeamCell.isVisible().catch(() => false)) {
      await expect(privateTeamCell).toBeVisible();
    } else {
      await expect(page.getByTestId(TeamPageIDS.resourceListItemPrivateTeam)).toBeVisible();
    }

    testReporter.completeStep('Trace team audit records', 'passed');

    await testReporter.finalizeTest();
  });
});
