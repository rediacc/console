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
    // Generate a unique team name for this test to avoid parallel conflicts
    const uniqueTeamName = `e2e-team-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    console.warn(`[Team Selection] Using unique team context: ${uniqueTeamName}`);
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
    } catch {
      // Fallback: if no matching API response, continue with UI check
      console.warn('No matching teams API response found, continuing with UI visibility check');
    }

    // Add extra wait for slower browsers (Firefox, WebKit) to complete Redux initialization
    await this.page.waitForTimeout(1000);

    // Try to wait for split view to appear (indicates team was auto-selected)
    try {
      await this.splitResourceViewContainer.waitFor({ state: 'visible', timeout: 5000 });
      console.warn('Team auto-selection succeeded - split view is visible');
      return; // Success - team was auto-selected
    } catch {
      console.warn('Split view not visible after 5s, attempting manual team selection fallback');
      // Check if we're in a "no team selected" state
      const noTeamMessage = this.page.locator('text=Select a team to view its resources');
      if (await noTeamMessage.isVisible().catch(() => false)) {
        console.warn('Found "no team selected" message - manual selection required');
      } else {
        console.warn('No clear "no team" message found - proceeding with manual selection attempt');
      }
    }

    // Fallback: If auto-selection didn't work, manually select the first team
    try {
      // Wait for team selector to be visible
      await this.teamSelector.waitFor({ state: 'visible', timeout: 3000 });

      // Click to open dropdown
      await this.clickWithRetry(this.teamSelector);
      await this.page.waitForTimeout(500);

      // Find and click first team option with better parallel execution handling
      const firstTeamOption = this.page.locator('[data-testid^="team-selector-option-"]').first();
      
      // Wait for team options with retry logic for parallel test environments
      let teamOptionVisible = false;
      let waitAttempts = 0;
      const maxWaitAttempts = 3;
      
      while (!teamOptionVisible && waitAttempts < maxWaitAttempts) {
        try {
          await firstTeamOption.waitFor({ state: 'visible', timeout: 2000 });
          teamOptionVisible = true;
          console.warn('Team option is visible, proceeding with selection');
        } catch {
          waitAttempts++;
          console.warn(`Team option not visible (attempt ${waitAttempts}), checking dropdown state...`);
          
          // Check if dropdown is still open
          const dropdownOpen = await this.teamSelector.getAttribute('aria-expanded');
          if (dropdownOpen !== 'true') {
            console.warn('Dropdown appears to be closed, reopening...');
            await this.clickWithRetry(this.teamSelector);
            await this.page.waitForTimeout(500);
          } else {
            console.warn('Dropdown is open but no options visible, waiting...');
            await this.page.waitForTimeout(1000);
          }
        }
      }
      
      if (!teamOptionVisible) {
        throw new Error('Team options did not become visible after multiple attempts');
      }
      
      // Click the team option
      await this.clickWithRetry(firstTeamOption);
      // Wait for the selection to take effect
      await this.page.waitForTimeout(1000);

      // Wait for selection to complete and split view to appear
      try {
        await this.splitResourceViewContainer.waitFor({ state: 'visible', timeout: 10000 });
        console.warn('Manual team selection fallback succeeded');
      } catch {
        console.error('Split view did not appear after team selection');
        throw new Error('Team selection failed: split view did not appear after selecting team');
      }
    } catch (error: unknown) {
      console.error('Team selection failed with error:', error);
      const errorMessage = error instanceof Error ? error.message : String(error);
      
      // Final fallback: try to create a team if none exist
      console.warn('Attempting final fallback: creating a new team...');
      try {
        // Navigate to teams page and create a team
        await this.page.goto('/console/organization/teams');
        await this.page.waitForLoadState('networkidle');
        
        const createButton = this.page.getByTestId('system-create-team-button');
        await createButton.waitFor({ state: 'visible', timeout: 5000 });
        await createButton.click();
        
        const teamNameInput = this.page.getByTestId('resource-modal-field-team-name-input');
        await teamNameInput.waitFor({ state: 'visible', timeout: 5000 });
        await teamNameInput.fill(uniqueTeamName);
        
        // Generate SSH key
        await this.page.getByTestId('vault-editor-generate-ssh-private-key').click();
        await this.page.getByTestId('vault-editor-generate-button').click();
        await this.page.getByTestId('vault-editor-apply-generated').click();
        
        // Submit
        await this.page.getByTestId('resource-modal-ok-button').click();
        
        // Wait for creation to complete
        await this.page.waitForTimeout(2000);
        
        // Navigate back to machines page
        await this.page.goto('/console/machines');
        await this.page.waitForLoadState('networkidle');
        
        console.warn('Team creation fallback succeeded');
        return; // Success with fallback
      } catch (createError) {
        console.error('Team creation fallback also failed:', createError);
        throw new Error(`Team selection failed: both auto-selection and manual fallback failed. Error: ${errorMessage}`);
      }
    }
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
