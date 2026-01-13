import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { test, expect } from '../../src/base/BaseTest';
import { skipIfNoVm } from '../../src/utils/vm';

// Machine FX Hello tests
// Focus: Run hello function on machine and verify success

// Skip: TestDataManager requires VM_WORKER_IPS which is not set in CI
test.describe
  .skip('Machine FX Hello Tests', () => {
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

    test('should run hello function on machine and verify success @resources @fx @hello @regression', async ({
      page,
      screenshotManager: _screenshotManager,
      testReporter,
      testDataManager,
    }) => {
      testReporter.startStep('Locate machine for FX execution');

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
            'Locate machine for FX execution',
            'skipped',
            'No machine rows found in resources table'
          );
          return;
        }

        // Use first available machine
        machineRow = machineCandidates.first();
      }

      testReporter.startStep('Open FX menu and navigate to hello');

      // Find and click remote button to open dropdown menu
      const remoteButton = machineRow.locator('[data-testid^="machine-remote-"]').first();
      await expect(remoteButton).toBeVisible({ timeout: 10000 });
      await remoteButton.click();

      // Wait for dropdown menu to appear
      const dropdownMenu = page.locator('.ant-dropdown-menu-root');
      await expect(dropdownMenu).toBeVisible({ timeout: 5000 });

      testReporter.startStep('Navigate to Run on Server submenu');

      // Find and hover over "Run on Server" to open submenu
      const runOnServerSubmenu = dropdownMenu
        .locator('.ant-dropdown-menu-submenu-title')
        .filter({ hasText: 'Run on Server' });
      await expect(runOnServerSubmenu).toBeVisible({ timeout: 5000 });
      await runOnServerSubmenu.hover();

      // Wait for functions popup to appear
      const functionsPopup = page.locator('#rc-menu-uuid-functions-popup');
      await expect(functionsPopup).toBeVisible({ timeout: 5000 });

      testReporter.startStep('Click hello function');

      // Click on hello menu item from the functions popup
      const helloMenuItem = functionsPopup.locator('li[data-menu-id*="function-hello"]');
      await expect(helloMenuItem).toBeVisible({ timeout: 5000 });
      await helloMenuItem.click();

      testReporter.startStep('Verify hello function execution success');

      // Verify success state in the queue trace modal (Wait up to 30s)
      const queueOverview = page.getByTestId('queue-trace-simple-overview');
      await expect(queueOverview).toBeVisible({ timeout: 5000 });
      await expect(
        queueOverview.locator('.queue-trace-status-icon .anticon-check-circle')
      ).toBeVisible({ timeout: 30000 });

      testReporter.completeStep('Verify hello function execution success', 'passed');

      testReporter.startStep('Close queue trace modal');

      // Close the queue trace modal
      const closeQueueButton = page.getByTestId('queue-trace-close-button');
      await expect(closeQueueButton).toBeVisible();
      await closeQueueButton.click();

      // Verify modal is closed
      await expect(queueOverview).not.toBeVisible({ timeout: 5000 });

      testReporter.completeStep('Close queue trace modal', 'passed');

      await testReporter.finalizeTest();
    });
  });
