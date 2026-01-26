import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';
import { UserPageIDs } from '@/pages/user/UserPageIDs';
import { ensureDrawerIsClosed } from '@/test-helpers/team-helpers';
import { ensureCreatedUser } from '@/test-helpers/user-helpers';
import { E2E_DEFAULTS } from '@/utils/constants';

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
    console.warn('[User Trace Test] Ensuring drawer is closed after navigation');
    await ensureDrawerIsClosed(page);
    console.warn('[User Trace Test] Drawer closed, proceeding with user verification');

    const verifyUserVisible = async (): Promise<boolean> => {
      // Ensure drawer is closed before attempting to find user
      await ensureDrawerIsClosed(page);

      // Additional CI-specific wait for DOM stability
      await page.waitForLoadState('domcontentloaded').catch(() => {});

      const searchInput = page.getByTestId('resource-list-search');
      if (await searchInput.isVisible().catch(() => false)) {
        await searchInput.fill('');
        await searchInput.fill(createdUser.email);
        await searchInput.press('Enter');
        // Wait for search results to update
        await page.waitForLoadState('networkidle').catch(() => {});
      }

      // Check both list and table views with multiple strategies
      const listItem = page.getByTestId(UserPageIDs.resourceListItem(createdUser.email));
      if (await listItem.isVisible().catch(() => false)) {
        return true;
      }

      // Try table view with more flexible visibility check
      const userTable = page.getByTestId(UserPageIDs.systemUserTable);
      if (await userTable.isVisible().catch(() => false)) {
        const emailCell = userTable.getByText(createdUser.email, { exact: true });
        if (await emailCell.isVisible().catch(() => false)) {
          return true;
        }
        // Also try scrolling the email into view
        try {
          await emailCell.scrollIntoViewIfNeeded().catch(() => {});
          return await emailCell.isVisible().catch(() => false);
        } catch {
          return false;
        }
      }

      return false;
    };

    // Add extra wait for CI environment stability
    await page.waitForLoadState('networkidle').catch(() => {});
    console.warn('[User Trace Test] Starting user visibility verification');
    await expect
      .poll(
        async () => {
          const result = await verifyUserVisible();
          console.warn(`[User Trace Test] User visibility check result: ${result}`);
          return result;
        },
        { timeout: 15000, intervals: [1000, 2000, 3000, 5000] }
      )
      .toBe(true);
    console.warn('[User Trace Test] User visibility verification passed');

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
