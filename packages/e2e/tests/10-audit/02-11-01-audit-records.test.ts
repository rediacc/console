import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { AuditPage } from '@/pages/audit/AuditPage';
import { ensureDrawerIsClosed } from '@/test-helpers/team-helpers';

test.describe('Audit Records Tests - Authenticated', () => {
  test.describe.configure({ mode: 'serial' });

  let loginPage: LoginPage;
  let auditPage: AuditPage;

  test.beforeEach(async ({ page }) => {
    // Audit is gated behind Expert mode; set before first page load
    await page.addInitScript(() => {
      localStorage.setItem('uiMode', 'expert');
    });

    loginPage = new LoginPage(page);
    auditPage = new AuditPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();

    const nav = new NavigationHelper(page);
    await nav.goToAudit();

    await ensureDrawerIsClosed(page);
  });

  test('should display audit page @audit @smoke', async ({ testReporter }) => {
    testReporter.startStep('Verify filter card is visible');
    await expect(auditPage.filterCard).toBeVisible({ timeout: 10000 });
    testReporter.completeStep('Verify filter card is visible', 'passed');

    testReporter.startStep('Verify table card is visible');
    await expect(auditPage.tableCard).toBeVisible({ timeout: 10000 });
    testReporter.completeStep('Verify table card is visible', 'passed');

    testReporter.startStep('Verify action buttons are visible');
    await expect(auditPage.refreshButton).toBeVisible();
    await expect(auditPage.exportButton).toBeVisible();
    testReporter.completeStep('Verify action buttons are visible', 'passed');

    await testReporter.finalizeTest();
  });

  test('should apply last 7 days date range filter @audit @regression', async ({
    testReporter,
  }) => {
    testReporter.startStep('Wait for filter card');
    await expect(auditPage.filterCard).toBeVisible({ timeout: 10000 });
    testReporter.completeStep('Wait for filter card', 'passed');

    testReporter.startStep('Select Last 7 Days preset');
    await auditPage.selectDatePreset('Last 7 Days');
    testReporter.completeStep('Select Last 7 Days preset', 'passed');

    testReporter.startStep('Verify date range is reflected in the picker');
    // After preset selection the start input (nested inside the RangePicker container) must have a date value
    await expect(auditPage.filterDate.locator('input').first()).not.toHaveValue('');
    testReporter.completeStep('Verify date range is reflected in the picker', 'passed');

    await testReporter.finalizeTest();
  });

  test('should filter audit records by entity type @audit @regression', async ({
    testReporter,
  }) => {
    testReporter.startStep('Wait for filter card and data to load');
    await expect(auditPage.filterCard).toBeVisible({ timeout: 10000 });
    await auditPage.waitForDataLoaded();
    testReporter.completeStep('Wait for filter card and data to load', 'passed');

    testReporter.startStep('Select Organization entity type');
    await auditPage.selectEntityType('Organization');
    testReporter.completeStep('Select Organization entity type', 'passed');

    testReporter.startStep('Verify Organization is shown in the entity filter');
    const selectionItem = auditPage.filterEntity.locator('.ant-select-selection-item');
    await expect(selectionItem).toContainText('Organization');
    testReporter.completeStep('Verify Organization is shown in the entity filter', 'passed');

    await testReporter.finalizeTest();
  });

  test('should refresh audit records @audit @regression', async ({ testReporter }) => {
    testReporter.startStep('Wait for filter card and refresh button');
    await expect(auditPage.filterCard).toBeVisible({ timeout: 10000 });
    await expect(auditPage.refreshButton).toBeEnabled({ timeout: 10000 });
    testReporter.completeStep('Wait for filter card and refresh button', 'passed');

    testReporter.startStep('Click refresh button');
    await auditPage.clickRefresh();
    testReporter.completeStep('Click refresh button', 'passed');

    testReporter.startStep('Verify table reloads after refresh');
    // Refresh button returns to enabled state once the request completes
    await expect(auditPage.refreshButton).toBeEnabled({ timeout: 15000 });
    await expect(auditPage.tableCard).toBeVisible();
    testReporter.completeStep('Verify table reloads after refresh', 'passed');

    await testReporter.finalizeTest();
  });

  test('should export audit records as csv @audit @regression', async ({ page, testReporter }) => {
    test.setTimeout(30000);

    testReporter.startStep('Wait for table to have data');
    await expect(auditPage.tableCard).toBeVisible({ timeout: 10000 });
    // Export is disabled when there is no data; wait for the button to be enabled
    await expect(auditPage.exportButton).toBeEnabled({ timeout: 15000 });
    testReporter.completeStep('Wait for table to have data', 'passed');

    testReporter.startStep('Trigger CSV export and verify download');
    const downloadPromise = page.waitForEvent('download', { timeout: 15000 });
    await auditPage.triggerCsvExport();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/audit.*\.csv$/i);
    testReporter.completeStep('Trigger CSV export and verify download', 'passed');

    await testReporter.finalizeTest();
  });
});
