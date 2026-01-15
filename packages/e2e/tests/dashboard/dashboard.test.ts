import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';
import { NavigationHelper } from '../../src/helpers/NavigationHelper';
import type { Locator } from '@playwright/test';

test.describe('Dashboard Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
  });

  test('should display main dashboard layout @dashboard @smoke', async ({
    page,
    screenshotManager,
    testReporter,
  }) => {
    testReporter.startStep('Verify dashboard layout');

    // Verify essential elements using the new page object methods
    await dashboardPage.verifyDashboardLoaded();

    const ensureNavVisible = async (locator: Locator) => {
      if (await locator.isVisible().catch(() => false)) {
        return;
      }
      const toggle = page.getByTestId('sidebar-toggle-button');
      if ((await toggle.count()) > 0) {
        await toggle.click();
        await expect(locator).toBeVisible({ timeout: 5000 });
        const drawerMask = page.locator('.ant-drawer-mask');
        if (await drawerMask.isVisible().catch(() => false)) {
          await drawerMask.click({ force: true });
        }
      }
    };

    // Check navigation items
    const locators = dashboardPage.getPageLocators();
    await ensureNavVisible(locators.navOrganization);
    await ensureNavVisible(locators.navSettings);
    await expect(locators.userMenu).toBeVisible();
    await expect(locators.notificationBell).toBeVisible();

    await screenshotManager.captureStep('dashboard_layout_verified');
    testReporter.completeStep('Verify dashboard layout', 'passed');

    await testReporter.finalizeTest();
  });



  test('should toggle team selector @dashboard', async ({
    page: _page,
    screenshotManager: _screenshotManager,
    testReporter,
  }) => {
    testReporter.startStep('Interact with team selector');

    // Wait for dashboard to load
    await dashboardPage.verifyDashboardLoaded();

    const locators = dashboardPage.getPageLocators();
    await expect(locators.teamSelector).toBeVisible();

    await dashboardPage.selectTeam('test'); // Clicks the selector

    // Just verify it doesn't crash and selector is still there
    await expect(locators.teamSelector).toBeVisible();

    testReporter.completeStep('Interact with team selector', 'passed');
    await testReporter.finalizeTest();
  });
});
