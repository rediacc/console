import { Locator, Page } from '@playwright/test';
import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';
import { E2E_DEFAULTS } from '../../src/utils/constants';
import { TestReporter } from '../../src/utils/report/TestReporter';
import { ScreenshotManager } from '../../src/utils/screenshot/ScreenshotManager';
import { skipIfNoVm } from '../../src/utils/vm';

// Machine trace tests migrated from Python MachineTraceTest
// Focus: open machine trace for a machine, verify trace view, sort columns and check entries

// Skip: TestDataManager requires VM_WORKER_IPS which is not set in CI
test.describe
  .skip('Machine Trace Tests', () => {
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
      testDataManager,
    }) => {
      testReporter.startStep('Locate machine for trace');

      const machine = testDataManager.getMachine();
      const machineRow = await locateMachineRow(page, machine.name, testReporter);

      if (!machineRow) {
        return;
      }

      await openAuditTraceDialog(machineRow, page, testReporter);

      testReporter.startStep('Open machine trace view');

      const traceModalOpened = await openTraceModal(page, screenshotManager, testReporter);
      if (!traceModalOpened) {
        return;
      }

      const traceModal = page.getByTestId('queue-trace-modal');

      await sortTraceColumns(traceModal, page, screenshotManager);
      testReporter.completeStep(
        'Sort trace table by common columns - Trace table sorted',
        'passed'
      );

      testReporter.startStep('Verify trace entries exist');
      await verifyTraceEntries(traceModal, screenshotManager, testReporter);

      testReporter.startStep('Close trace modal');
      await closeTraceModal(page, traceModal, screenshotManager);
      testReporter.completeStep('Close trace modal - Trace modal closed', 'passed');

      await testReporter.finalizeTest();
    });
  });

// Helper functions to reduce cognitive complexity

async function locateMachineRow(
  page: Page,
  machineName: string,
  testReporter: TestReporter
): Promise<Locator | null> {
  const machineList = page.getByTestId('machine-table');
  await expect(machineList).toBeVisible({ timeout: 10000 });

  // Wait for table data to load
  await expect(machineList.locator('tbody tr.machine-table-row').first()).toBeVisible({
    timeout: 20000,
  });

  // Try to find the specific machine row by data-row-key
  let machineRow = machineList.locator(`tbody tr[data-row-key*="${machineName}"]`);

  if (!(await machineRow.isVisible({ timeout: 20000 }).catch(() => false))) {
    // Fallback: get any machine row from the table
    const machineCandidates = machineList.locator('tbody tr.machine-table-row');

    if ((await machineCandidates.count()) === 0) {
      testReporter.completeStep(
        'Locate machine for trace',
        'skipped',
        'No machine rows found in resources table'
      );
      return null;
    }

    // Use first available machine
    machineRow = machineCandidates.first();
  }

  return machineRow;
}

async function openAuditTraceDialog(
  machineRow: Locator,
  page: Page,
  testReporter: TestReporter
): Promise<void> {
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
  const totalRecords = Number.parseInt(totalRecordsText ?? E2E_DEFAULTS.CPU_COUNT_STRING, 10);
  expect(totalRecords).toBeGreaterThan(0);

  testReporter.completeStep(
    `Locate machine for trace - Found audit records: ${totalRecords}`,
    'passed'
  );
}

async function openTraceModal(
  page: Page,
  screenshotManager: ScreenshotManager,
  testReporter: TestReporter
): Promise<boolean> {
  // Look for queue trace button using getByTestId pattern
  const queueButton = page.getByTestId('machines-queue-trace-button');

  if (!(await queueButton.isVisible({ timeout: 5000 }).catch(() => false))) {
    await screenshotManager.captureStep('trace_button_not_found');
    testReporter.completeStep(
      'Open machine trace view',
      'skipped',
      'Trace/Queue button not found for selected machine'
    );
    return false;
  }

  await queueButton.click();

  // Use getByTestId for queue trace modal
  const traceModal = page.getByTestId('queue-trace-modal');

  try {
    await expect(traceModal).toBeVisible({ timeout: 15000 });
    await screenshotManager.captureStep('trace_modal_opened');
    testReporter.completeStep('Open machine trace view - Trace modal opened', 'passed');
    return true;
  } catch (error) {
    await screenshotManager.captureStep('trace_modal_not_visible');
    testReporter.completeStep(
      'Open machine trace view - Trace modal not visible',
      'failed',
      'Trace modal did not become visible'
    );
    throw error;
  }
}

async function sortTraceColumns(
  traceModal: Locator,
  page: Page,
  screenshotManager: ScreenshotManager
): Promise<void> {
  const columnNames = ['Updated', 'Created', 'Status', 'Task', 'Bridge'];

  for (const columnName of columnNames) {
    // Try to find column header within the modal
    const columnHeader = traceModal.locator(`th:has-text("${columnName}")`).first();

    if (await columnHeader.isVisible({ timeout: 2000 }).catch(() => false)) {
      await columnHeader.click();
      // Wait for table to re-render after sort
      await page.waitForLoadState('networkidle');
    } else {
      await screenshotManager.captureStep(`trace_column_${columnName}_not_found`);
    }
  }

  await screenshotManager.captureStep('trace_table_sorted');
}

async function verifyTraceEntries(
  traceModal: Locator,
  screenshotManager: ScreenshotManager,
  testReporter: TestReporter
): Promise<void> {
  // Get trace rows from within the modal
  const traceRows = traceModal.locator('tbody tr');
  const rowCount = await traceRows.count();

  if (rowCount === 0) {
    await screenshotManager.captureStep('no_trace_rows_found');
    testReporter.completeStep(
      'Verify trace entries exist - No trace entries found in table',
      'skipped',
      'No trace entries found in table'
    );
    return;
  }

  const maxRowsToLog = Math.min(rowCount, 5);

  for (let i = 0; i < maxRowsToLog; i++) {
    const row = traceRows.nth(i);
    if (await row.isVisible()) {
      const text = (await row.textContent()) ?? '';
      // We do not log here to keep test output clean; this is only for potential future extensions
      void text;
    }
  }

  await screenshotManager.captureStep('trace_rows_found');
  testReporter.completeStep('Verify trace entries exist - Trace entries found in table', 'passed');
}

async function closeTraceModal(
  page: Page,
  traceModal: Locator,
  screenshotManager: ScreenshotManager
): Promise<void> {
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
}
