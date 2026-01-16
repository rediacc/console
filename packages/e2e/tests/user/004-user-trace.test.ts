import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { UserPageIDs } from '../../pages/user/UserPageIDs';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import { E2E_DEFAULTS } from '../../src/utils/constants';
import { ensureDrawerIsClosed } from '../helpers/team-helpers';
import { ensureCreatedUser } from '../helpers/user-helpers';

test.describe('Team Trace Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should trace team user audit records @system @organization @audit @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
    testDataManager,
  }) => {
    test.setTimeout(60000);
    testReporter.startStep('Navigate to Organization Users section');

    const createdUser = await ensureCreatedUser(page, testDataManager);

    // Navigate to Organization > Users
    const nav = new NavigationHelper(page);
    await nav.goToOrganizationUsers();

    // Ensure drawer is closed after navigation (critical for mobile/tablet)
    await ensureDrawerIsClosed(page);

    const verifyUserVisible = async (): Promise<boolean> => {
      // Ensure drawer is closed before attempting to find user
      await ensureDrawerIsClosed(page);

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

    testReporter.startStep('Trace user audit records');

    const traceButton = page.getByTestId(UserPageIDs.systemUserTraceButton(createdUser.email));
    if (await traceButton.isVisible().catch(() => false)) {
      await ensureDrawerIsClosed(page);
      await traceButton.click();
    } else {
      const listItem = page.getByTestId(UserPageIDs.resourceListItem(createdUser.email));
      await expect(listItem).toBeVisible({ timeout: 5000 });
      const actionsButton = listItem.getByRole('button', { name: /actions/i });
      await expect(actionsButton).toBeVisible();
      await ensureDrawerIsClosed(page);
      await actionsButton.click();
      const traceMenuItem = page.getByRole('menuitem', { name: /trace/i });
      await expect(traceMenuItem).toBeVisible({ timeout: 5000 });
      await traceMenuItem.click();
    }
    const auditRecordsText = await page
      .getByTestId(UserPageIDs.auditTraceVisibleRecords)
      .locator('strong')
      .textContent();
    const recordCount = Number.parseInt(auditRecordsText ?? E2E_DEFAULTS.CPU_COUNT_STRING);
    expect(recordCount).toBeGreaterThan(0);
    const auditModal = page.getByTestId('audit-trace-modal');
    await auditModal.getByRole('button', { name: 'Close' }).click();
    testReporter.completeStep('Trace user audit records', 'passed');
    await testReporter.finalizeTest();
  });
});
