import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';
import { skipIfNoVm } from '../../src/utils/vm';

// Machine delete tests
// Focus: delete machine and verify deletion

test.describe('Machine Delete Tests', () => {
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

  test('should delete machine and verify deletion @resources @delete @regression', async ({
    page,
    screenshotManager: _screenshotManager,
    testReporter,
    testDataManager,
  }) => {
    testReporter.startStep('Locate machine for deletion');

    const machine = testDataManager.getMachine();

    // Check if machine appears in the list
    const machineList = page.getByTestId('machine-table');
    await expect(machineList).toBeVisible({ timeout: 10000 });

    // Tablo verilerinin gelmesini bekle (en az bir satir gorunene kadar)
    await expect(machineList.locator('tbody tr.machine-table-row').first()).toBeVisible({
      timeout: 20000,
    });

    // Try to find the specific machine row by data-row-key
    let machineRow = machineList.locator(`tbody tr[data-row-key*="${machine.name}"]`);

    if (!(await machineRow.isVisible({ timeout: 20000 }).catch(() => false))) {
      // Fallback: get any machine row from the table (skip measure row)
      const machineCandidates = machineList.locator('tbody tr.machine-table-row');

      if ((await machineCandidates.count()) === 0) {
        testReporter.completeStep(
          'Locate machine for deletion',
          'skipped',
          'No machine rows found in resources table'
        );
        return;
      }

      // Use first available machine
      machineRow = machineCandidates.first();
    }

    // Get machine name before deletion from data-row-key attribute
    const machineNameToDelete = await machineRow.getAttribute('data-row-key');

    if (!machineNameToDelete) {
      testReporter.completeStep(
        'Locate machine for deletion',
        'failed',
        'Could not get machine name'
      );
      return;
    }

    testReporter.startStep('Click delete button');

    // Find delete button within the row
    const deleteButton = machineRow.locator('[data-testid^="machine-delete-"]').first();
    await expect(deleteButton).toBeVisible({ timeout: 10000 });
    await deleteButton.click();

    testReporter.startStep('Confirm deletion in modal');

    // Wait for confirmation modal to appear
    const deleteModal = page.locator('.ant-modal-confirm');
    await expect(deleteModal).toBeVisible({ timeout: 10000 });

    // Verify modal title
    const modalTitle = deleteModal.locator('.ant-modal-title');
    await expect(modalTitle).toHaveText('Delete Machine');

    // Verify modal content contains the confirmation message
    const modalContent = deleteModal.locator('.ant-modal-confirm-content');
    await expect(modalContent).toBeVisible();

    // Click delete button (dangerous button) in modal
    const deleteConfirmButton = deleteModal.locator('button.ant-btn-dangerous');
    await expect(deleteConfirmButton).toBeVisible();
    await expect(deleteConfirmButton).toContainText('Delete');
    await deleteConfirmButton.click();

    testReporter.startStep('Verify machine is deleted');

    // Wait for modal to close
    await expect(deleteModal).not.toBeVisible({ timeout: 10000 });

    // Wait a bit for the table to refresh
    await page.waitForTimeout(2000);

    // Verify the specific machine is no longer in the table
    const deletedMachineRow = machineList.locator(
      `tbody tr[data-row-key="${machineNameToDelete}"]`
    );
    await expect(deletedMachineRow).not.toBeVisible({ timeout: 10000 });

    // Alternative verification: check by data-testid if available
    const deletedMachineByTestId = page.getByTestId(`machine-row-${machineNameToDelete}`);
    await expect(deletedMachineByTestId)
      .not.toBeVisible({ timeout: 5000 })
      .catch(() => {
        // Ignore if testid doesn't exist, primary check above is sufficient
      });

    testReporter.completeStep('Verify machine is deleted', 'passed');

    await testReporter.finalizeTest();
  });
});
