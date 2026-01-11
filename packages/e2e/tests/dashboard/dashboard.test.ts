import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';

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
    testReporter 
  }) => {
    await testReporter.startStep('Verify dashboard layout');
    
    // Verify essential elements using the new page object methods
    await dashboardPage.verifyDashboardLoaded();
    
    // Check navigation items
    const locators = dashboardPage.getPageLocators();
    await expect(locators.navOrganization).toBeVisible();
    await expect(locators.navSettings).toBeVisible();
    await expect(locators.userMenu).toBeVisible();
    await expect(locators.notificationBell).toBeVisible();
    
    await screenshotManager.captureStep('dashboard_layout_verified');
    await testReporter.completeStep('Verify dashboard layout', 'passed');
    
    await testReporter.finalizeTest();
  });

  test('should navigate between main sections @dashboard', async ({ 
    page, 
    screenshotManager, 
    testReporter 
  }) => {
    await testReporter.startStep('Navigate sections');
    
    // Machine is default, so it should be visible
    const locators = dashboardPage.getPageLocators();
    await expect(locators.splitResourceViewContainer).toBeVisible();

    // Go to Settings (assuming it navigates or shows something)
    // For now just verify the button is clickable
    await dashboardPage.openDeviceSettings();
    await page.waitForLoadState('networkidle');
    await screenshotManager.captureStep('settings_navigated');
    
    // Go back to machines
    await dashboardPage.navigateToMachines();
    await page.waitForLoadState('networkidle');
    await expect(locators.splitResourceViewContainer).toBeVisible();
    await screenshotManager.captureStep('machines_navigated');

    await testReporter.completeStep('Navigate sections', 'passed');
    await testReporter.finalizeTest();
  });

  test('should display machines view elements @dashboard', async ({ 
    page, 
    screenshotManager, 
    testReporter 
  }) => {
    await testReporter.startStep('Verify machines view');
    
    const locators = dashboardPage.getPageLocators();

    // Verify machine-specific buttons
    await expect(locators.machinesCreateButton).toBeVisible();
    await expect(locators.machinesTestRefreshButton).toBeVisible();
    
    // Verify layout containers
    await expect(locators.splitResourceViewLeftPanel).toBeVisible();
    
    // Verify resource list (either empty or container)
    // We check if either the list container or empty state is visible
    const listVisible = await locators.resourceListContainer.isVisible();
    const emptyVisible = await locators.resourceListEmpty.isVisible();
    expect(listVisible || emptyVisible).toBeTruthy();

    await testReporter.completeStep('Verify machines view', 'passed');
    await testReporter.finalizeTest();
  });

  test('should toggle team selector @dashboard', async ({ 
    page, 
    screenshotManager, 
    testReporter 
  }) => {
    await testReporter.startStep('Interact with team selector');
    
    const locators = dashboardPage.getPageLocators();
    await expect(locators.teamSelector).toBeVisible();
    
    await dashboardPage.selectTeam('test'); // Clicks the selector
    
    // Just verify it doesn't crash and selector is still there
    await expect(locators.teamSelector).toBeVisible();
    
    await testReporter.completeStep('Interact with team selector', 'passed');
    await testReporter.finalizeTest();
  });
});