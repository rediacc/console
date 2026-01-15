import { Page, Locator } from '@playwright/test';
import { BasePage } from '../../src/base/BasePage';

export class DashboardPage extends BasePage {
  // Navigation
  private readonly navOrganization: Locator;
  private readonly navMachines: Locator;
  private readonly navSettings: Locator;

  // Header / Top Bar
  private readonly notificationBell: Locator;
  private readonly userMenu: Locator;
  private readonly teamSelector: Locator;

  // Main Content
  private readonly mainContent: Locator;

  // Machines / Resources Views
  private readonly machinesCreateButton: Locator;
  private readonly machinesTestRefreshButton: Locator;
  private readonly splitResourceViewContainer: Locator;
  private readonly splitResourceViewLeftPanel: Locator;
  private readonly resourceListContainer: Locator;
  private readonly resourceListEmpty: Locator;

  // Global
  private readonly toasterContainer: Locator;

  constructor(page: Page) {
    super(page, '/console/machines');

    // Navigation
    this.navOrganization = page.locator('[data-testid="main-nav-organization"]');
    this.navMachines = page.locator('[data-testid="main-nav-machines"]');
    this.navSettings = page.locator('[data-testid="main-nav-settings"]');

    // Header / Top Bar
    this.notificationBell = page.locator('[data-testid="notification-bell"]');
    this.userMenu = page.locator('[data-testid="user-menu-button"]');
    this.teamSelector = page.locator('[data-testid="team-selector"]');

    // Main Content
    this.mainContent = page.locator('[data-testid="main-content"]');

    // Machines / Resources
    this.machinesCreateButton = page.locator('[data-testid="machines-create-machine-button"]');
    this.machinesTestRefreshButton = page.locator(
      '[data-testid="machines-test-and-refresh-button"]'
    );
    this.splitResourceViewContainer = page.locator('[data-testid="split-resource-view-container"]');
    this.splitResourceViewLeftPanel = page.locator(
      '[data-testid="split-resource-view-left-panel"]'
    );
    this.resourceListContainer = page.locator('[data-testid="resource-list-container"]');
    this.resourceListEmpty = page.locator('[data-testid="resource-list-empty"]');

    // Global
    this.toasterContainer = page.locator('[data-testid="themed-toaster-container"]');
  }

  getPageLocators(): Record<string, Locator> {
    return {
      navOrganization: this.navOrganization,
      navMachines: this.navMachines,
      navSettings: this.navSettings,
      notificationBell: this.notificationBell,
      userMenu: this.userMenu,
      teamSelector: this.teamSelector,
      mainContent: this.mainContent,
      machinesCreateButton: this.machinesCreateButton,
      machinesTestRefreshButton: this.machinesTestRefreshButton,
      splitResourceViewContainer: this.splitResourceViewContainer,
      splitResourceViewLeftPanel: this.splitResourceViewLeftPanel,
      resourceListContainer: this.resourceListContainer,
      resourceListEmpty: this.resourceListEmpty,
      toasterContainer: this.toasterContainer,
    };
  }

  async verifyDashboardLoaded(): Promise<void> {
    await this.verifyElementVisible(this.mainContent);
    await this.ensureTestIdVisible('main-nav-machines');
    await this.verifyElementVisible(this.page.locator('[data-testid="main-nav-machines"]:visible'));
  }

  async waitForTeamSelection(timeout = 10000): Promise<void> {
    // Wait for teams API to complete first
    // This is more reliable than networkidle which has browser-specific timing issues
    try {
      await this.page.waitForResponse(
        (response) => {
          const url = response.url();
          return response.status() === 200 &&
                 url.includes('/api/') &&
                 (url.includes('Team') || url.includes('Organization'));
        },
        { timeout }
      );
    } catch (e) {
      // Fallback: if no matching API response, continue with UI check
      console.warn('No matching teams API response found, continuing with UI visibility check');
    }

    // Add extra wait for slower browsers (Firefox, WebKit) to complete Redux initialization
    await this.page.waitForTimeout(1000);

    // Then wait for Redux auto-selection to trigger resource view
    // Split view appears after team is auto-selected and machines query starts
    // Use longer timeout for Firefox/WebKit
    await this.splitResourceViewContainer.waitFor({ state: 'visible', timeout: 20000 });
  }

  async clickUserMenu(): Promise<void> {
    await this.clickWithRetry(this.userMenu);
  }

  async clickNotificationBell(): Promise<void> {
    await this.clickWithRetry(this.notificationBell);
  }

  async openDeviceSettings(): Promise<void> {
    await this.ensureTestIdVisible('main-nav-settings');
    const visibleNavSettings = this.page.locator('[data-testid="main-nav-settings"]:visible');
    await this.clickWithRetry(visibleNavSettings);
  }

  async openOrganization(): Promise<void> {
    await this.ensureTestIdVisible('main-nav-organization');
    const visibleNavOrganization = this.page.locator(
      '[data-testid="main-nav-organization"]:visible'
    );
    await this.clickWithRetry(visibleNavOrganization);
  }

  async navigateToMachines(): Promise<void> {
    await this.ensureTestIdVisible('main-nav-machines');
    const visibleNavMachines = this.page.locator('[data-testid="main-nav-machines"]:visible');
    await this.clickWithRetry(visibleNavMachines);
  }

  // Helper for dynamic team tags
  getTeamTag(teamName: string): Locator {
    // Note: The ID in the list was 'team-selector-tag-Private Team', so we assume dynamic part
    return this.page.locator(`[data-testid="team-selector-tag-${teamName}"]`);
  }

  async selectTeam(teamName: string): Promise<void> {
    // Verify selector is visible before interacting
    await this.teamSelector.waitFor({ state: 'visible', timeout: 5000 });

    // Click to open the dropdown
    await this.clickWithRetry(this.teamSelector);

    // Wait for dropdown to fully open (Ant Design animation)
    await this.page.waitForTimeout(500);

    // If a specific team is needed, click it in the dropdown
    if (teamName && teamName !== 'test') {
      const option = this.page.locator(`[data-testid="team-selector-option-${teamName}"]`);
      await option.waitFor({ state: 'visible', timeout: 5000 });
      await this.clickWithRetry(option);
      // Wait for selection to complete
      await this.page.waitForTimeout(300);
    } else {
      // For test purposes, just close the dropdown by pressing Escape
      await this.page.keyboard.press('Escape');
      // Wait for dropdown to fully close
      await this.page.waitForTimeout(500);
    }

    // Verify selector is still visible after interaction
    await this.teamSelector.waitFor({ state: 'visible', timeout: 3000 });
  }

  async clickCreateMachine(): Promise<void> {
    await this.clickWithRetry(this.machinesCreateButton);
  }

  async clickTestAndRefresh(): Promise<void> {
    await this.clickWithRetry(this.machinesTestRefreshButton);
  }

  async verifyToastVisible(): Promise<void> {
    await this.verifyElementVisible(this.toasterContainer);
  }
}
