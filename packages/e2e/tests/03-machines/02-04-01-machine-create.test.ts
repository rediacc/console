import { test, expect } from '@/base/BaseTest';
import { NavigationHelper } from '@/helpers/NavigationHelper';
import { LoginPage } from '@/pages/auth/LoginPage';
import { ensureDrawerIsClosed } from '@/test-helpers/team-helpers';
import { skipIfNoVm } from '@/utils/vm';

test.describe('Machine Creation Tests - Authenticated', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.navigate();
    await loginPage.performQuickLogin();

    const nav = new NavigationHelper(page);
    await nav.goToMachines();

    await ensureDrawerIsClosed(page);
  });

  test.afterEach(async ({ page }) => {
    const modal = page.getByTestId('resource-modal-form');
    if (await modal.isVisible()) {
      const cancelButton = page.getByTestId('resource-modal-cancel-button');
      if (await cancelButton.isVisible()) {
        await cancelButton.click();
        await expect(modal).not.toBeVisible();
      }
    }
  });

  test('should open machine creation dialog @resources @smoke', async ({ page, testReporter }) => {
    testReporter.startStep('Open machine creation dialog');

    const createMachineButton = page.getByTestId('machines-create-machine-button');
    await expect(createMachineButton).toBeVisible({ timeout: 10000 });
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
    page,
    testReporter,
    testDataManager,
  }) => {
    skipIfNoVm();
    test.setTimeout(120000);

    testReporter.startStep('Open machine creation dialog');

    const createMachineButton = page.getByTestId('machines-create-machine-button');
    await expect(createMachineButton).toBeVisible({ timeout: 10000 });
    await expect(createMachineButton).toBeEnabled();
    await createMachineButton.click();

    const createMachineDialog = page.getByTestId('resource-modal-form');
    await expect(createMachineDialog).toBeVisible();

    testReporter.completeStep('Open machine creation dialog', 'passed');

    testReporter.startStep('Fill machine details');

    const testMachine = testDataManager.createTemporaryMachine();

    await page.getByTestId('resource-modal-field-machineName-input').fill(testMachine.name);
    await page.getByTestId('vault-editor-field-ip').fill(testMachine.ip);

    const userField = page.getByTestId('vault-editor-field-user');
    const passwordField = page.getByTestId('vault-editor-field-ssh_password');

    if (await userField.isVisible()) {
      await userField.fill(testMachine.user);
    }
    if (await passwordField.isVisible()) {
      await passwordField.fill(testMachine.password);
    }

    testReporter.startStep('Test Connection');
    await page.getByTestId('vault-editor-test-connection').click();

    const vaultSection = page.getByTestId('resource-modal-vault-editor-section');
    const connectionAlert = vaultSection.getByRole('alert');

    await expect(connectionAlert).toBeVisible({ timeout: 60000 });
    await expect(connectionAlert.locator('.ant-alert-title .ant-space-item').nth(1)).toContainText(
      'Compatible',
      { timeout: 30000 }
    );
    testReporter.completeStep('Test Connection', 'passed');

    testReporter.completeStep('Fill machine details', 'passed');

    testReporter.startStep('Submit machine creation');

    const submitButton = page.getByTestId('resource-modal-ok-button');
    await expect(submitButton).toBeEnabled();
    await submitButton.click();

    const queueOverview = page.getByTestId('queue-trace-simple-overview');
    await expect(queueOverview).toBeVisible({ timeout: 10000 });

    await expect(
      queueOverview.locator('.queue-trace-status-icon .anticon-check-circle')
    ).toBeVisible({ timeout: 45000 });

    const closeQueueButton = page.getByTestId('queue-trace-close-button');
    await expect(closeQueueButton).toBeVisible();
    await closeQueueButton.click();

    testReporter.completeStep('Submit machine creation', 'passed');

    testReporter.startStep('Verify machine created');

    const machineTable = page.getByTestId('machines-machines-table');
    await expect(machineTable.getByText(testMachine.name)).toBeVisible({ timeout: 15000 });

    testReporter.completeStep('Verify machine created', 'passed');

    await testReporter.finalizeTest();
  });

  test('should validate required fields @resources', async ({ page, testReporter }) => {
    testReporter.startStep('Open machine creation dialog');

    const createMachineButton = page.getByTestId('machines-create-machine-button');
    await expect(createMachineButton).toBeVisible({ timeout: 10000 });
    await createMachineButton.click();

    const createMachineDialog = page.getByTestId('resource-modal-form');
    await expect(createMachineDialog).toBeVisible();

    testReporter.completeStep('Open machine creation dialog', 'passed');

    testReporter.startStep('Test validation');

    const submitButton = page.getByTestId('resource-modal-ok-button');
    await expect(submitButton).toBeDisabled();

    testReporter.completeStep('Test validation', 'passed');

    await testReporter.finalizeTest();
  });

  test('should cancel machine creation @resources', async ({ page, testReporter }) => {
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
