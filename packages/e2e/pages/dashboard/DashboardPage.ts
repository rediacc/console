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
    this.machinesTestRefreshButton = page.locator('[data-testid="machines-test-and-refresh-button"]');
    this.splitResourceViewContainer = page.locator('[data-testid="split-resource-view-container"]');
    this.splitResourceViewLeftPanel = page.locator('[data-testid="split-resource-view-left-panel"]');
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
      toasterContainer: this.toasterContainer
    };
  }

  async verifyDashboardLoaded(): Promise<void> {
    await this.verifyElementVisible(this.mainContent);
    await this.verifyElementVisible(this.navMachines);
  }

  async clickUserMenu(): Promise<void> {
    await this.clickWithRetry(this.userMenu);
  }

  async clickNotificationBell(): Promise<void> {
    await this.clickWithRetry(this.notificationBell);
  }
  
  async openDeviceSettings(): Promise<void> {
    await this.clickWithRetry(this.navSettings);
  }

  async openOrganization(): Promise<void> {
    await this.clickWithRetry(this.navOrganization);
  }

  async navigateToMachines(): Promise<void> {
    await this.clickWithRetry(this.navMachines);
  }

  // Helper for dynamic team tags
  getTeamTag(teamName: string): Locator {
    // Note: The ID in the list was 'team-selector-tag-Private Team', so we assume dynamic part
    return this.page.locator(`[data-testid="team-selector-tag-${teamName}"]`);
  }

  async selectTeam(teamName: string): Promise<void> {
    await this.clickWithRetry(this.teamSelector);
    // Logic for selecting team from dropdown would go here, 
    // assuming the tags might also be used in the selector or similar.
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