import { Page } from '@playwright/test';

/**
 * Navigation test IDs used across the application.
 * These must match the data-testid attributes in the web app's routes.tsx
 */
export const NavTestIds = {
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
 * a generous timeout to account for CI slowness.
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
  constructor(private page: Page) {}

  // ==========================================================================
  // Organization Navigation
  // ==========================================================================

  /**
   * Navigate to Organization > Users
   */
  async goToOrganizationUsers(): Promise<void> {
    await this.expandOrganizationMenu();
    await this.clickSubNavItem(NavTestIds.subNavOrganizationUsers);
  }

  /**
   * Navigate to Organization > Teams
   */
  async goToOrganizationTeams(): Promise<void> {
    await this.expandOrganizationMenu();
    await this.clickSubNavItem(NavTestIds.subNavOrganizationTeams);
  }

  /**
   * Navigate to Organization > Access
   */
  async goToOrganizationAccess(): Promise<void> {
    await this.expandOrganizationMenu();
    await this.clickSubNavItem(NavTestIds.subNavOrganizationAccess);
  }

  // ==========================================================================
  // Settings Navigation
  // ==========================================================================

  /**
   * Navigate to Settings > Profile
   */
  async goToSettingsProfile(): Promise<void> {
    await this.expandSettingsMenu();
    await this.clickSubNavItem(NavTestIds.subNavSettingsProfile);
  }

  /**
   * Navigate to Settings > Organization
   */
  async goToSettingsOrganization(): Promise<void> {
    await this.expandSettingsMenu();
    await this.clickSubNavItem(NavTestIds.subNavSettingsOrganization);
  }

  /**
   * Navigate to Settings > Infrastructure
   */
  async goToSettingsInfrastructure(): Promise<void> {
    await this.expandSettingsMenu();
    await this.clickSubNavItem(NavTestIds.subNavSettingsInfrastructure);
  }

  // ==========================================================================
  // Ceph Navigation
  // ==========================================================================

  /**
   * Navigate to Ceph > Clusters
   */
  async goToCephClusters(): Promise<void> {
    await this.expandCephMenu();
    await this.clickSubNavItem(NavTestIds.subNavCephClusters);
  }

  /**
   * Navigate to Ceph > Pools
   */
  async goToCephPools(): Promise<void> {
    await this.expandCephMenu();
    await this.clickSubNavItem(NavTestIds.subNavCephPools);
  }

  /**
   * Navigate to Ceph > Machines
   */
  async goToCephMachines(): Promise<void> {
    await this.expandCephMenu();
    await this.clickSubNavItem(NavTestIds.subNavCephMachines);
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
    await this.expandSubmenu(
      NavTestIds.mainNavOrganization,
      NavTestIds.subNavOrganizationUsers
    );
  }

  /**
   * Expand the Settings menu if not already expanded.
   * Waits for Profile sub-nav item to become visible as indicator of expansion.
   */
  private async expandSettingsMenu(): Promise<void> {
    await this.expandSubmenu(
      NavTestIds.mainNavSettings,
      NavTestIds.subNavSettingsProfile
    );
  }

  /**
   * Expand the Ceph menu if not already expanded.
   * Waits for Clusters sub-nav item to become visible as indicator of expansion.
   */
  private async expandCephMenu(): Promise<void> {
    await this.expandSubmenu(
      NavTestIds.mainNavCeph,
      NavTestIds.subNavCephClusters
    );
  }

  /**
   * Generic method to expand a submenu and wait for a sub-item to be visible.
   *
   * @param parentTestId - Test ID of the parent menu item to click
   * @param childTestId - Test ID of a child item to wait for (indicates menu expanded)
   */
  private async expandSubmenu(parentTestId: string, childTestId: string): Promise<void> {
    const childLocator = this.page.getByTestId(childTestId);

    // Check if submenu is already expanded
    const isAlreadyVisible = await childLocator.isVisible().catch(() => false);
    if (isAlreadyVisible) {
      return; // Menu already expanded, no need to click parent
    }

    // Click parent to expand submenu
    await this.page.getByTestId(parentTestId).click();

    // Wait for submenu to expand (child item becomes visible)
    await childLocator.waitFor({
      state: 'visible',
      timeout: SUBMENU_VISIBLE_TIMEOUT,
    });
  }

  /**
   * Click a main navigation item (no submenu).
   */
  private async clickMainNavItem(testId: string): Promise<void> {
    await this.page.getByTestId(testId).click();
  }

  /**
   * Click a sub-navigation item after ensuring it's visible.
   */
  private async clickSubNavItem(testId: string): Promise<void> {
    const locator = this.page.getByTestId(testId);
    await locator.waitFor({ state: 'visible', timeout: SUBMENU_VISIBLE_TIMEOUT });
    await locator.click();
  }
}
