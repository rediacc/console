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

  test('should create a new machine @resources @regression', async ({
    testDataManager,
  }, testInfo) => {
    const testReporter = new TestReporter(page, testInfo);

    // Step 1: Open machine creation dialog
    testReporter.startStep('Open machine creation dialog');

    const createMachineButton = page.getByTestId('machines-create-machine-button');
    await expect(createMachineButton).toBeVisible({ timeout: 10000 });
    await createMachineButton.click();

    // Use form locator to avoid strict mode issues with the modal container
    const createMachineDialog = page.getByTestId('resource-modal-form');
    await expect(createMachineDialog).toBeVisible();

    testReporter.completeStep('Open machine creation dialog', 'passed');

    // Step 2: Fill machine details with unique name
    testReporter.startStep('Fill machine details');

    const testMachine = testDataManager.getMachine();

    // Fill basic info
    await page.getByTestId('resource-modal-field-machineName-input').fill(testMachine.name);
    await page.getByTestId('vault-editor-field-ip').fill(testMachine.ip);

    // Fill Vault info
    const userField = page.getByTestId('vault-editor-field-user');
    const passwordField = page.getByTestId('vault-editor-field-ssh_password');
    if (await userField.isVisible()) {
      await userField.fill(testMachine.user);
    }
    if (await passwordField.isVisible()) {
      await passwordField.fill(testMachine.password);
    }

    // Test Connection
    await page.getByTestId('vault-editor-test-connection').click();
    const vaultSection = page.getByTestId('resource-modal-vault-editor-section');
    const connectionAlert = vaultSection.getByRole('alert');
    await expect(connectionAlert).toBeVisible({ timeout: 50000 });
    await expect(connectionAlert.locator('.ant-alert-title .ant-space-item').nth(1)).toContainText(
      'Compatible'
    );

    testReporter.startStep('Submit machine creation');

    const submitButton = page.getByTestId('resource-modal-ok-button');
    await submitButton.click();

    // Verify success state in the queue trace modal (Wait up to 30s)
    const queueOverview = page.getByTestId('queue-trace-simple-overview');
    await expect(queueOverview).toBeVisible({ timeout: 5000 });
    await expect(
      queueOverview.locator('.queue-trace-status-icon .anticon-check-circle')
    ).toBeVisible({ timeout: 30000 });

    const closeQueueButton = page.getByTestId('queue-trace-close-button');
    await expect(closeQueueButton).toBeVisible();
    await closeQueueButton.click();

    testReporter.completeStep('Submit machine creation', 'passed');

    testReporter.startStep('Verify machine created');

    // Check if machine appears in the list
    const machineList = page.getByTestId('machines-machines-table');
    const newMachineRow = machineList.locator(`text=${testMachine.name}`);

    try {
      await expect(newMachineRow).toBeVisible({ timeout: 10000 });
      testReporter.completeStep('Verify machine created', 'passed');
    } catch {
      testReporter.completeStep('Verify machine created', 'failed', 'Machine not found in list');
    }

    await testReporter.finalizeTest();
  });

  test('should validate required fields @resources', async ({ testDataManager: _dm }, testInfo) => {
    const testReporter = new TestReporter(page, testInfo);

    testReporter.startStep('Open machine creation dialog');

    const createMachineButton = page.getByTestId('machines-create-machine-button');
    await expect(createMachineButton).toBeVisible({ timeout: 10000 });
    await createMachineButton.click();

    const createMachineDialog = page.getByTestId('resource-modal-form');
    await expect(createMachineDialog).toBeVisible();

    testReporter.completeStep('Open machine creation dialog', 'passed');

    testReporter.startStep('Test validation without filling fields');

    const submitButton = page.getByTestId('resource-modal-ok-button');

    // Verify that submit button is disabled when required fields are empty
    const isDisabled = await submitButton.isDisabled();

    if (isDisabled) {
      console.warn('Submit button is disabled - validation working correctly');
      testReporter.completeStep('Test validation without filling fields', 'passed');
    } else {
      console.warn('Submit button is NOT disabled - validation may not be working');
      testReporter.completeStep(
        'Test validation without filling fields',
        'failed',
        'Submit button should be disabled when fields are empty'
      );
    }

    await testReporter.finalizeTest();
  });

  test('should cancel machine creation @resources', async ({ testDataManager: _dm }, testInfo) => {
    const testReporter = new TestReporter(page, testInfo);

    testReporter.startStep('Open machine creation dialog');

    const createMachineButton = page.getByTestId('machines-create-machine-button');
    await expect(createMachineButton).toBeVisible({ timeout: 10000 });

    await createMachineButton.click();

    const createMachineDialog = page.getByTestId('resource-modal-form');
    await expect(createMachineDialog).toBeVisible();

    testReporter.completeStep('Open machine creation dialog', 'passed');

    testReporter.startStep('Fill partial data and cancel');

    const nameField = page.getByTestId('resource-modal-field-machineName-input');
    await nameField.fill('test-machine-to-cancel');

    const cancelButton = page.getByTestId('resource-modal-cancel-button');
    await cancelButton.click();

    await expect(createMachineDialog).not.toBeVisible();

    testReporter.completeStep('Fill partial data and cancel', 'passed');

    await testReporter.finalizeTest();
  });
});
