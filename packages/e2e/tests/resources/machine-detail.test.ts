import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';
import { skipIfNoVm } from '../../src/utils/vm';

// Machine detail tests
// Focus: open machine detail sidebar and verify machine information

// Skip: TestDataManager requires VM_WORKER_IPS which is not set in CI
test.describe
  .skip('Machine Detail Tests', () => {
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

    test('should open machine detail sidebar and verify machine name @resources @detail @regression', async ({
      page,
      screenshotManager: _screenshotManager,
      testReporter,
      testDataManager,
    }) => {
      testReporter.startStep('Locate machine for detail view');

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
            'Locate machine for detail view',
            'skipped',
            'No machine rows found in resources table'
          );
          return;
        }

        // Use first available machine
        machineRow = machineCandidates.first();
      }

      // Find view details button within the row
      const viewDetailsButton = machineRow
        .locator('[data-testid^="machine-view-details-"]')
        .first();
      await expect(viewDetailsButton).toBeVisible({ timeout: 10000 });
      await viewDetailsButton.click();

      testReporter.startStep('Open machine detail sidebar');

      // Wait for detail sidebar to open
      const detailPanel = page.getByTestId('unified-detail-panel');
      await expect(detailPanel).toBeVisible({ timeout: 10000 });

      testReporter.startStep('Verify machine name in sidebar');

      // Get machine name from sidebar
      const machineNameElement = page.getByTestId('vault-status-machine-name');
      await expect(machineNameElement).toBeVisible({ timeout: 10000 });

      const displayedMachineName = await machineNameElement.textContent();

      // Verify machine name matches
      expect(displayedMachineName?.trim()).toBe(machine.name);

      testReporter.startStep('Close detail sidebar');

      // Use getByTestId for collapse button
      const collapseButton = page.getByTestId('vault-status-collapse');

      if (await collapseButton.isVisible({ timeout: 10000 }).catch(() => false)) {
        await collapseButton.click();
      } else {
        // Fallback to escape key if button not found
        await page.keyboard.press('Escape');
      }

      await expect(detailPanel).not.toBeVisible({ timeout: 10000 });
      testReporter.completeStep('Close detail sidebar', 'passed');

      await testReporter.finalizeTest();
    });
  });
