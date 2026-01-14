import { Page } from '@playwright/test';

/**
 * Navigation test IDs used across the application.
 * These must match the data-testid attributes in the web app's routes.tsx
 */
const NavTestIds = {
  // Main navigation items
  mainNavOrganization: 'main-nav-organization',
  mainNavMachines: 'main-nav-machines',
  mainNavSettings: 'main-nav-settings',
  mainNavStorage: 'main-nav-storage',
  mainNavCeph: 'main-nav-ceph',
  mainNavCredentials: 'main-nav-credentials',
  mainNavQueue: 'main-nav-queue',
  mainNavAudit: 'main-nav-audit',
  mainNavDashboard: 'main-nav-dashboard',

  // Organization sub-navigation
  subNavOrganizationUsers: 'sub-nav-organization-users',
  subNavOrganizationTeams: 'sub-nav-organization-teams',
  subNavOrganizationAccess: 'sub-nav-organization-access',

  // Settings sub-navigation
  subNavSettingsProfile: 'sub-nav-settings-profile',
  subNavSettingsOrganization: 'sub-nav-settings-organization',
  subNavSettingsInfrastructure: 'sub-nav-settings-infrastructure',

  // Ceph sub-navigation
  subNavCephClusters: 'sub-nav-ceph-clusters',
  subNavCephPools: 'sub-nav-ceph-pools',
  subNavCephMachines: 'sub-nav-ceph-machines',
} as const;

/**
 * Default timeout for waiting for submenu items to become visible.
 * ProLayout animations typically complete within 300-500ms, but we use
 * a generous timeout to account for test environment slowness.
 */
const SUBMENU_VISIBLE_TIMEOUT = 5000;

/**
 * Navigation helper that handles ProLayout submenu expansion timing.
 *
 * The Ant Design Pro ProLayout component animates submenu expansion.
 * Tests that click a parent menu item and immediately try to click
 * a sub-item will fail because the sub-item isn't visible yet.
 *
 * This helper ensures sub-menu items are visible before clicking them.
 *
 * @example
 * ```typescript
 * const nav = new NavigationHelper(page);
 * await nav.goToOrganizationUsers();
 * ```
 */
export class NavigationHelper {
  private static readonly SIDEBAR_TOGGLE_TEST_ID = 'sidebar-toggle-button';
  private static readonly SIDEBAR_TOGGLE_LABEL = /expand sidebar|collapse sidebar/i;

  constructor(private readonly page: Page) {}

  // ==========================================================================
  // Organization Navigation
  // ==========================================================================

  /**
   * Navigate to Organization > Users
   */
  async goToOrganizationUsers(): Promise<void> {
    await this.navigateToSubNav(NavTestIds.mainNavOrganization, NavTestIds.subNavOrganizationUsers);
  }

  /**
   * Navigate to Organization > Teams
   */
  async goToOrganizationTeams(): Promise<void> {
    await this.navigateToSubNav(NavTestIds.mainNavOrganization, NavTestIds.subNavOrganizationTeams);
  }

  /**
   * Navigate to Organization > Access
   */
  async goToOrganizationAccess(): Promise<void> {
    await this.navigateToSubNav(
      NavTestIds.mainNavOrganization,
      NavTestIds.subNavOrganizationAccess
    );
  }

  // ==========================================================================
  // Settings Navigation
  // ==========================================================================

  /**
   * Navigate to Settings > Profile
   */
  async goToSettingsProfile(): Promise<void> {
    await this.navigateToSubNav(NavTestIds.mainNavSettings, NavTestIds.subNavSettingsProfile);
  }

  /**
   * Navigate to Settings (top-level)
   */
  async goToSettings(): Promise<void> {
    await this.clickMainNavItem(NavTestIds.mainNavSettings);
  }

  /**
   * Navigate to Settings > Organization
   */
  async goToSettingsOrganization(): Promise<void> {
    await this.navigateToSubNav(NavTestIds.mainNavSettings, NavTestIds.subNavSettingsOrganization);
  }

  /**
   * Navigate to Settings > Infrastructure
   */
  async goToSettingsInfrastructure(): Promise<void> {
    await this.navigateToSubNav(
      NavTestIds.mainNavSettings,
      NavTestIds.subNavSettingsInfrastructure
    );
  }

  // ==========================================================================
  // Ceph Navigation
  // ==========================================================================

  /**
   * Navigate to Ceph > Clusters
   */
  async goToCephClusters(): Promise<void> {
    await this.navigateToSubNav(NavTestIds.mainNavCeph, NavTestIds.subNavCephClusters);
  }

  /**
   * Navigate to Ceph > Pools
   */
  async goToCephPools(): Promise<void> {
    await this.navigateToSubNav(NavTestIds.mainNavCeph, NavTestIds.subNavCephPools);
  }

  /**
   * Navigate to Ceph > Machines
   */
  async goToCephMachines(): Promise<void> {
    await this.navigateToSubNav(NavTestIds.mainNavCeph, NavTestIds.subNavCephMachines);
  }

  // ==========================================================================
  // Top-level Navigation (no submenu)
  // ==========================================================================

  /**
   * Navigate to Dashboard
   */
  async goToDashboard(): Promise<void> {
    await this.clickMainNavItem(NavTestIds.mainNavDashboard);
  }

  /**
   * Navigate to Machines
   */
  async goToMachines(): Promise<void> {
    await this.clickMainNavItem(NavTestIds.mainNavMachines);
  }

  /**
   * Navigate to Storage
   */
  async goToStorage(): Promise<void> {
    await this.clickMainNavItem(NavTestIds.mainNavStorage);
  }

  /**
   * Navigate to Credentials
   */
  async goToCredentials(): Promise<void> {
    await this.clickMainNavItem(NavTestIds.mainNavCredentials);
  }

  /**
   * Navigate to Queue
   */
  async goToQueue(): Promise<void> {
    await this.clickMainNavItem(NavTestIds.mainNavQueue);
  }

  /**
   * Navigate to Audit
   */
  async goToAudit(): Promise<void> {
    await this.clickMainNavItem(NavTestIds.mainNavAudit);
  }

  // ==========================================================================
  // Private Helper Methods
  // ==========================================================================

  /**
   * Expand the Organization menu if not already expanded.
   * Waits for Users sub-nav item to become visible as indicator of expansion.
   */
  private async expandOrganizationMenu(): Promise<void> {
    await this.expandSubmenu(NavTestIds.mainNavOrganization, NavTestIds.subNavOrganizationUsers);
  }

  /**
   * Expand the Settings menu if not already expanded.
   * Waits for Profile sub-nav item to become visible as indicator of expansion.
   */
  private async expandSettingsMenu(): Promise<void> {
    await this.expandSubmenu(NavTestIds.mainNavSettings, NavTestIds.subNavSettingsProfile);
  }

  /**
   * Expand the Ceph menu if not already expanded.
   * Waits for Clusters sub-nav item to become visible as indicator of expansion.
   */
  private async expandCephMenu(): Promise<void> {
    await this.expandSubmenu(NavTestIds.mainNavCeph, NavTestIds.subNavCephClusters);
  }

  /**
   * Generic method to expand a submenu and wait for a sub-item to be visible.
   *
   * @param parentTestId - Test ID of the parent menu item to click
   * @param childTestId - Test ID of a child item to wait for (indicates menu expanded)
   */
  private async expandSubmenu(parentTestId: string, childTestId: string): Promise<void> {
    // Check if submenu is already expanded
    const isAlreadyVisible = await this.page
      .locator(`[data-testid="${childTestId}"]:visible`)
      .isVisible()
      .catch(() => false);
    if (isAlreadyVisible) {
      return; // Menu already expanded, no need to click parent
    }

    await this.ensureNavVisible(parentTestId);

    // Click parent to expand submenu (prefer visible, fallback to drawer)
    const parentLocator = this.page.locator(`[data-testid="${parentTestId}"]:visible`);
    if (await parentLocator.isVisible().catch(() => false)) {
      await parentLocator.click();
    } else {
      const toggle = await this.getSidebarToggle();
      await toggle.click();
      const drawer = this.page.locator('.ant-drawer');
      await drawer.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      const drawerItem = drawer.locator(`[data-testid="${parentTestId}"]`);
      await drawerItem.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      await drawerItem.click();
    }

    // Wait for submenu to expand (child item becomes visible)
    await this.page.locator(`[data-testid="${childTestId}"]:visible`).waitFor({
      state: 'visible',
      timeout: SUBMENU_VISIBLE_TIMEOUT,
    });
  }

  /**
   * Click a main navigation item (no submenu).
   */
  private async clickMainNavItem(testId: string): Promise<void> {
    await this.ensureNavVisible(testId);
    const locator = this.page.locator(`[data-testid="${testId}"]:visible`);
    if (await locator.isVisible().catch(() => false)) {
      await locator.click();
      return;
    }

    const toggle = await this.getSidebarToggle();
    if ((await toggle.count()) > 0) {
      await toggle.click();
      const drawer = this.page.locator('.ant-drawer');
      await drawer.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      const drawerItem = drawer.locator(`[data-testid="${testId}"]`);
      await drawerItem.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      await drawerItem.click();
    }
  }

  /**
   * Click a sub-navigation item after ensuring it's visible.
   */
  private async clickSubNavItem(testId: string): Promise<void> {
    const locator = this.page.locator(`[data-testid="${testId}"]:visible`);
    if (await locator.isVisible().catch(() => false)) {
      await locator.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      await locator.click();
      return;
    }

    const toggle = await this.getSidebarToggle();
    if ((await toggle.count()) > 0) {
      await toggle.click();
      const drawer = this.page.locator('.ant-drawer');
      await drawer.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      const drawerItem = drawer.locator(`[data-testid="${testId}"]`);
      await drawerItem.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      await drawerItem.click();
    }
  }

  private async ensureNavVisible(testId: string): Promise<void> {
    const target = this.page.locator(`[data-testid="${testId}"]:visible`);
    if (await target.isVisible().catch(() => false)) {
      return;
    }

    const toggle = await this.getSidebarToggle();
    if ((await toggle.count()) === 0) {
      return;
    }

    await toggle.click();
    try {
      await target.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      return;
    } catch {
      // If the sidebar was already open, the first click may have collapsed it.
      await toggle.click();
      await target.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
    }
  }

  private async navigateToSubNav(parentTestId: string, childTestId: string): Promise<void> {
    const toggle = await this.getSidebarToggle();
    if ((await toggle.count()) > 0) {
      await toggle.click();
      const drawer = this.page.locator('.ant-drawer');
      await drawer.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      const drawerParent = drawer.locator(`[data-testid="${parentTestId}"]`);
      await drawerParent.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      await drawerParent.click();

      const drawerChild = drawer.locator(`[data-testid="${childTestId}"]`);
      await drawerChild.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      await drawerChild.click();
      const mask = this.page.locator('.ant-drawer-mask');
      if (await mask.isVisible().catch(() => false)) {
        await mask.click({ force: true });
      } else {
        await toggle.click({ force: true });
      }
      const maskVisible = await mask.isVisible().catch(() => false);
      if (maskVisible) {
        await this.page.evaluate(() => {
          const overlay = document.querySelector<HTMLElement>('.ant-drawer-mask');
          if (overlay) {
            overlay.style.pointerEvents = 'none';
            overlay.style.opacity = '0';
          }
        });
      }
      await drawer.waitFor({ state: 'hidden', timeout: SUBMENU_VISIBLE_TIMEOUT }).catch(() => {});
      return;
    }

    await this.ensureNavVisible(parentTestId);
    const parentLocator = this.page.locator(`[data-testid="${parentTestId}"]:visible`);
    if (await parentLocator.isVisible().catch(() => false)) {
      await parentLocator.click();
      const childLocator = this.page.locator(`[data-testid="${childTestId}"]:visible`);
      await childLocator.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
      await childLocator.click();
    }
  }

  private async getSidebarToggle() {
    const candidates = [
      this.page.getByTestId(NavigationHelper.SIDEBAR_TOGGLE_TEST_ID),
      this.page.getByRole('button', {
        name: NavigationHelper.SIDEBAR_TOGGLE_LABEL,
      }),
      this.page.locator('button:has(.anticon-menu)'),
      this.page.locator('.anticon-menu'),
    ];

    for (const candidate of candidates) {
      if ((await candidate.count()) > 0) {
        return candidate;
      }
    }

    return candidates[0];
  }
}
