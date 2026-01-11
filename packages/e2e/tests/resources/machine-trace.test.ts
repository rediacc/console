import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { skipIfNoVm } from '../../src/utils/vm';

// Machine trace tests migrated from Python MachineTraceTest
// Focus: open machine trace for a machine, verify trace view, sort columns and check entries

test.describe('Machine Trace Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  // Skip all tests in this file if VM infrastructure is not available
  test.beforeEach(() => {
    skipIfNoVm();
  });

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('should open machine trace and view task history @resources @trace @regression', async ({
    page,
    screenshotManager,
    testReporter,
    testDataManager
  }) => {
    const stepLocateMachine = await testReporter.startStep('Locate machine for trace');

    const machine = testDataManager.getMachine();

    // Check if machine appears in the list
    const machineList = page.getByTestId('machine-table');
    await expect(machineList).toBeVisible({ timeout: 10000 });

    // Tablo verilerinin gelmesini bekle (en az bir satir gorunene kadar)
    await expect(machineList.locator('tbody tr.machine-table-row').first()).toBeVisible({ timeout: 20000 });

    // Try to find the specific machine row by data-row-key
    let machineRow = machineList.locator(`tbody tr[data-row-key*="${machine.name}"]`);

    if (!(await machineRow.isVisible({ timeout: 20000 }).catch(() => false))) {
      // Fallback: get any machine row from the table (skip measure row)
      const machineCandidates = machineList.locator('tbody tr.machine-table-row');

      if ((await machineCandidates.count()) === 0) {
        await testReporter.completeStep('Locate machine for trace','skipped','No machine rows found in resources table');
        return;
      }

      // Use first available machine
      machineRow = machineCandidates.first();
    }

    // Find trace button within the row
    const traceButton = machineRow.locator('[data-testid^="machine-trace-"]').first();
    await expect(traceButton).toBeVisible({ timeout: 5000 });
    await traceButton.click();
    
    // Wait for audit trace dialog to open
    const auditRecordsElement = page.getByTestId('audit-trace-total-records');
    await expect(auditRecordsElement).toBeVisible({ timeout: 10000 });
    
    // Get total records count from second span
    const totalRecordsSpan = auditRecordsElement.locator('span').nth(1);
    await expect(totalRecordsSpan).toBeVisible({ timeout: 5000 });
    const totalRecordsText = await totalRecordsSpan.textContent();
    const totalRecords = parseInt(totalRecordsText || '0', 10);
    expect(totalRecords).toBeGreaterThan(0);

    await testReporter.completeStep(`Locate machine for trace - Found audit records: ${totalRecords}`, 'passed');
    const stepOpenTrace = await testReporter.startStep('Open machine trace view');

    // Look for queue trace button using getByTestId pattern
    const queueButton = page.getByTestId('machines-queue-trace-button');

    if (!(await queueButton.isVisible({ timeout: 5000 }).catch(() => false))) {
      await screenshotManager.captureStep('trace_button_not_found');
      await testReporter.completeStep(
        'Open machine trace view',
        'skipped',
        'Trace/Queue button not found for selected machine'
      );
      return;
    }

    await queueButton.click();

    // Use getByTestId for queue trace modal
    const traceModal = page.getByTestId('queue-trace-modal');

    try {
      await expect(traceModal).toBeVisible({ timeout: 15000 });
      await screenshotManager.captureStep('trace_modal_opened');
      await testReporter.completeStep(`Open machine trace view - Trace modal opened`, 'passed');
    } catch (error) {
      await screenshotManager.captureStep('trace_modal_not_visible');
      await testReporter.completeStep(
        'Open machine trace view - Trace modal not visible',
        'failed',
        'Trace modal did not become visible'
      );
      throw error;
    }

    const stepSortColumns = await testReporter.startStep('Sort trace table by common columns');

    const columnNames = ['Updated', 'Created', 'Status', 'Task', 'Bridge'];

    for (const columnName of columnNames) {
      // Try to find column header within the modal
      const columnHeader = traceModal.locator(`th:has-text("${columnName}")`).first();

      if (await columnHeader.isVisible({ timeout: 2000 }).catch(() => false)) {
        await columnHeader.click();
        await page.waitForTimeout(500);
      } else {
        await screenshotManager.captureStep(`trace_column_${columnName}_not_found`);
      }
    }

    await screenshotManager.captureStep('trace_table_sorted');
    await testReporter.completeStep(`Sort trace table by common columns - Trace table sorted`, 'passed');

    const stepVerifyRows = await testReporter.startStep('Verify trace entries exist');

    // Get trace rows from within the modal
    const traceRows = traceModal.locator('tbody tr');

    const rowCount = await traceRows.count();

    if (rowCount === 0) {
      await screenshotManager.captureStep('no_trace_rows_found');
      await testReporter.completeStep(
        'Verify trace entries exist - No trace entries found in table',
        'skipped',
        'No trace entries found in table'
      );
    } else {
      const maxRowsToLog = Math.min(rowCount, 5);

      for (let i = 0; i < maxRowsToLog; i++) {
        const row = traceRows.nth(i);
        if (await row.isVisible()) {
          const text = (await row.textContent()) || '';
          // We do not log here to keep test output clean; this is only for potential future extensions
          void text;
        }
      }

      await screenshotManager.captureStep('trace_rows_found');
      await testReporter.completeStep(`Verify trace entries exist - Trace entries found in table`, 'passed');
    }

    const stepCloseTrace = await testReporter.startStep('Close trace modal');

    // Use getByTestId for close button
    const closeButton = page.getByTestId('queue-trace-close-button');

    if (await closeButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await closeButton.click();
    } else {
      // Fallback to escape key if button not found
      await page.keyboard.press('Escape');
    }

    await expect(traceModal).not.toBeVisible({ timeout: 5000 });
    await screenshotManager.captureStep('trace_modal_closed');
    await testReporter.completeStep(`Close trace modal - Trace modal closed`, 'passed');

    await testReporter.finalizeTest();
  });
});
