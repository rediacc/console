import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';

test.describe('2.11.1 Audit Records', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.navigate();
    await loginPage.performQuickLogin();

    // The Audit page requires "Expert Mode" to be visible in the navigation.
    const userMenuButton = page.getByTestId('user-menu-button');
    await expect(userMenuButton).toBeVisible();
    await userMenuButton.click();

    const modeToggle = page.getByTestId('main-mode-toggle');
    await expect(modeToggle).toBeVisible();

    // Ant Design Segmented: Expert mode is the second item
    await modeToggle.locator('.ant-segmented-item', { hasText: 'Expert' }).click();

    // Close user menu by clicking outside
    await page.keyboard.press('Escape');

    const nav = new NavigationHelper(page);
    await nav.goToAudit();
  });

  test('should view audit records', async ({ page, testReporter }) => {
    testReporter.startStep('Verify Audit page navigation');
    await expect(page.getByTestId('audit-filter-card')).toBeVisible({ timeout: 15000 });
    testReporter.completeStep('Verify Audit page navigation', 'passed');

    testReporter.startStep('Select Date Range filter');
    const datePicker = page.getByTestId('audit-filter-date');
    await datePicker.click();

    // Select a range in the picker (click two cells in the visible calendar)
    // Using first().click() as there might be two calendar panels visible
    await page.getByRole('gridcell', { name: '10' }).first().click();
    await page.getByRole('gridcell', { name: '20' }).first().click();

    // Since Audit has showTime, we need to click the 'OK' button to finalize selection
    const okButton = page.locator('.ant-picker-ok button');
    if (await okButton.isVisible()) {
      await okButton.click();
    }

    // Wait for picker to close
    await expect(page.locator('.ant-picker-panel:visible')).toHaveCount(0);
    testReporter.completeStep('Select Date Range filter', 'passed');

    testReporter.startStep('Select Entity Type filter: Organization');
    const entitySelect = page.getByTestId('audit-filter-entity');
    await entitySelect.click();

    // Ant Design Select options are rendered in a portal at the end of body
    const entityOption = page.getByRole('option', { name: 'organization', exact: false });
    await entityOption.waitFor({ state: 'visible' });
    await entityOption.click();

    // Ensure dropdown is closed
    await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);
    testReporter.completeStep('Select Entity Type filter: Organization', 'passed');

    testReporter.startStep('Click Refresh button');
    const refreshButton = page.getByTestId('audit-refresh-button');
    await refreshButton.click();

    // Wait for loading to finish if visible (ReloadOutlined icon becomes static or button stops loading state)
    await expect(refreshButton).not.toHaveAttribute('class', /ant-btn-loading/);
    testReporter.completeStep('Click Refresh button', 'passed');

    testReporter.startStep('Click Export button');
    const exportButton = page.getByTestId('audit-export-button');

    // The export button might be disabled if there's no data in the range
    if (await exportButton.isEnabled()) {
      await exportButton.click();

      // Select CSV option from the dropdown
      const csvOption = page.getByTestId('audit-export-csv');
      await csvOption.waitFor({ state: 'visible' });
      await csvOption.click();

      testReporter.completeStep('Click Export button', 'passed');
    } else {
      testReporter.completeStep('Click Export button', 'skipped');
    }

    await testReporter.finalizeTest();
  });
});
