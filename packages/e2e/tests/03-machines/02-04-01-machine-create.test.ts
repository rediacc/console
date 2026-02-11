import { Page } from '@playwright/test';
import { test, expect } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';
import { TestReporter } from '@/utils/report/TestReporter';
import { skipIfNoVm } from '@/utils/vm';

test.describe('Machine Creation Tests - Authenticated', () => {
  test.describe.configure({ mode: 'serial' });

  // Skip all tests in this file if VM infrastructure is not available
  test.beforeEach(() => {
    skipIfNoVm();
  });

  let page: Page;
  let loginPage: LoginPage;

  test.beforeAll(async ({ browser }) => {
    // Create a single page to be shared across all tests
    page = await browser.newPage();
    loginPage = new LoginPage(page);

    // Initial navigation
    await loginPage.navigate();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test.beforeEach(async () => {
    // Check if based on localstorage/session we are logged in
    // logic: If we are on the login page or have the login button, perform login.
    // Otherwise, assume session is active (or restore if possible, but user said no file).
    // User requested: "login işlemeleri için tarayıcının localstorage'ını kullan" -> implied: check state

    const isLoginPage = page.url().includes('/login');
    const loginButtonVisible = await page
      .locator('[data-testid="login-submit-button"]')
      .isVisible()
      .catch(() => false);

    if (isLoginPage || loginButtonVisible) {
      await loginPage.performQuickLogin();
    }
  });

  test.afterEach(async () => {
    // Cleanup: Close modal if left open to ensure next test starts clean
    const modal = page.getByTestId('resource-modal-form');
    if (await modal.isVisible()) {
      const cancelButton = page.getByTestId('resource-modal-cancel-button');
      if (await cancelButton.isVisible()) {
        await cancelButton.click();
        await expect(modal).not.toBeVisible();
      }
    }
  });

  test('should open machine creation dialog @resources @smoke', async ({
    testDataManager: _testDataManager,
  }, testInfo) => {
    // Manually instantiate reporter with shared page
    const testReporter = new TestReporter(page, testInfo);

    testReporter.startStep('Navigate to machines section');

    const createMachineButton = page.getByTestId('machines-create-machine-button');
    await expect(createMachineButton).toBeVisible({ timeout: 10000 });

    testReporter.startStep('Open machine creation dialog');

    await createMachineButton.click();

    const createMachineDialog = page.getByTestId('resource-modal-form');
    await expect(createMachineDialog).toBeVisible();

    testReporter.completeStep('Open machine creation dialog', 'passed');

    testReporter.startStep('Verify dialog fields');

    const nameField = page.getByTestId('resource-modal-field-machineName-input');
    const ipField = page.getByTestId('vault-editor-field-ip');

    await expect(nameField).toBeVisible();
    await expect(ipField).toBeVisible();

    testReporter.completeStep('Verify dialog fields', 'passed');

    await testReporter.finalizeTest();
  });
});
