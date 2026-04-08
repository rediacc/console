import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';

test.describe('2.10.1 Queue Operations', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.navigate();
    await loginPage.performQuickLogin();

    // The Queue page requires "Expert Mode" to be visible in the navigation.
    // Toggle UI mode to Expert if necessary.
    const userMenuButton = page.getByTestId('user-menu-button');
    await expect(userMenuButton).toBeVisible();
    await userMenuButton.click();

    const modeToggle = page.getByTestId('main-mode-toggle');
    await expect(modeToggle).toBeVisible();

    // Ant Design Segmented: Expert mode is the second item
    await modeToggle.locator('.ant-segmented-item').last().click();

    // Close user menu by clicking outside
    await page.mouse.click(0, 0);

    const nav = new NavigationHelper(page);
    await nav.goToQueue();
  });

  test('should perform queue operations', async ({ page, testReporter }) => {
    testReporter.startStep('Verify Queue page navigation');
    await expect(page.getByTestId('queue-page-container')).toBeVisible({ timeout: 15000 });
    testReporter.completeStep('Verify Queue page navigation', 'passed');

    testReporter.startStep('Select Team filter');
    const teamSelect = page.getByTestId('queue-filter-team');
    await teamSelect.click();
    // Wait for dropdown to be visible and click an option
    const teamOption = page.locator('.ant-select-dropdown:visible .ant-select-item-option').first();
    await teamOption.waitFor({ state: 'visible' });
    await teamOption.click();
    // Ensure dropdown is closed before next select to avoid locator conflicts
    await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);
    testReporter.completeStep('Select Team filter', 'passed');

    testReporter.startStep('Select Region filter');
    const regionSelect = page.getByTestId('queue-filter-region');
    await regionSelect.click();
    const regionOption = page.locator('.ant-select-dropdown:visible .ant-select-item-option').first();
    await regionOption.waitFor({ state: 'visible' });
    await regionOption.click();
    await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);
    testReporter.completeStep('Select Region filter', 'passed');

    testReporter.startStep('Select Date Range filter');
    const datePicker = page.getByTestId('queue-filter-date').first();
    await datePicker.click();
    // Select a range in the picker (click two cells in the visible calendar)
    const calendarCell = page.locator('.ant-picker-panel:visible .ant-picker-cell-inner');
    await calendarCell.first().click();
    await calendarCell.last().click();
    // Wait for picker to close
    await expect(page.locator('.ant-picker-panel:visible')).toHaveCount(0);
    testReporter.completeStep('Select Date Range filter', 'passed');

    testReporter.startStep('Switch between Queue tabs');
    const tabs = ['active', 'completed', 'cancelled', 'failed'];
    for (const tab of tabs) {
      testReporter.startStep(`Switch to ${tab} tab`);
      const tabLocator = page.getByTestId(`queue-tab-${tab}`);
      await tabLocator.click();

      // Verify tab is active - Ant Design Tabs use internal state, 
      // we check if our label is within the active tab container
      const activeTabContainer = page.locator('.ant-tabs-tab-active');
      await expect(activeTabContainer.getByTestId(`queue-tab-${tab}`)).toBeVisible();
      testReporter.completeStep(`Switch to ${tab} tab`, 'passed');
    }
    testReporter.completeStep('Switch between Queue tabs', 'passed');

    await testReporter.finalizeTest();
  });
});
