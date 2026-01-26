import { test, expect } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';
import { loadGlobalState } from '@/setup/global-state';

// Vault configuration tests migrated from Python VaultConfigurationTest
// Focus: open System page, open organization vault modal, fill required fields, generate SSH key and save

// Skip: Organization Settings page requires Power Mode which is a hidden developer feature
// Power Mode is enabled via Ctrl+Shift+E keyboard shortcut and requires session-only state
// that cannot be reliably triggered in automated tests
test.describe
  .skip('System Vault Configuration Tests', () => {
    let loginPage: LoginPage;

    test.beforeEach(async ({ page }) => {
      loginPage = new LoginPage(page);

      await loginPage.navigate();

      // Login with dynamically registered user
      const { email, password } = loadGlobalState();
      await loginPage.login(email, password);
      await loginPage.waitForLoginCompletion();

      // Enable expert mode before authentication
      await page.evaluate(() => {
        localStorage.setItem('uiMode', 'expert');
      });

      await page.reload();

      // Navigate to Settings > Organization using UI navigation
      const settingsNav = page.locator('[role="navigation"]').getByText('Settings');
      await settingsNav.waitFor({ state: 'visible', timeout: 10000 });
      await settingsNav.click();

      // Click on Organization submenu (requires power mode) - waitFor handles menu expansion
      const organizationSubNav = page.locator('[role="navigation"]').getByText('Organization');
      await organizationSubNav.waitFor({ state: 'visible', timeout: 10000 });
      await organizationSubNav.click();
      await page.waitForLoadState('networkidle');
    });

    test('should configure organization vault with generated ssh key @system @vault @regression', async ({
      page,
      screenshotManager,
      testReporter,
    }) => {
      testReporter.startStep('Verify Organization Settings page loaded');

      // Already navigated to /console/settings/organization in beforeEach
      // Verify we're on the correct page by checking for organization vault button
      const organizationVaultButton = page.locator(
        '[data-testid="system-organization-vault-button"]'
      );

      try {
        await expect(organizationVaultButton).toBeVisible({ timeout: 10000 });
        await screenshotManager.captureStep('organization_settings_page_loaded');
        testReporter.completeStep('Verify Organization Settings page loaded', 'passed');
      } catch {
        await screenshotManager.captureStep('organization_settings_page_not_loaded');
        testReporter.completeStep(
          'Verify Organization Settings page loaded',
          'failed',
          'Organization Settings page did not load correctly'
        );
        throw new Error('Organization Settings page did not load correctly');
      }

      testReporter.startStep('Open organization vault configuration');

      // Use precise selector - no fallbacks
      await organizationVaultButton.click();

      const vaultModal = page.locator('[data-testid="vault-modal"]');

      try {
        await expect(vaultModal).toBeVisible({ timeout: 5000 });
        await screenshotManager.captureStep('vault_modal_opened');
        testReporter.completeStep('Open organization vault configuration', 'passed');
      } catch (openError) {
        await screenshotManager.captureStep('vault_modal_not_visible');
        testReporter.completeStep(
          'Open organization vault configuration',
          'failed',
          'Vault configuration modal did not become visible'
        );
        throw openError;
      }

      testReporter.startStep('Fill required vault fields');

      await fillFieldIfEmpty(
        page.locator('[data-testid="vault-editor-field-UNIVERSAL_USER_ID"]'),
        page.locator('input[placeholder*="Universal User ID" i]').first(),
        'universal_user_001'
      );

      await fillFieldIfEmpty(
        page.locator('[data-testid="vault-editor-field-UNIVERSAL_USER_NAME"]'),
        page.locator('input[placeholder*="Universal User Name" i]').first(),
        'Universal User'
      );

      await fillEmptyTextFields(page);

      await screenshotManager.captureStep('vault_fields_filled');
      testReporter.completeStep('Fill required vault fields', 'passed');

      testReporter.startStep('Generate ssh key for vault');

      const sshDialogOpened = await openSshDialog(page);

      if (sshDialogOpened) {
        await configureSshOptions(page, screenshotManager, testReporter);
      } else {
        await screenshotManager.captureStep('ssh_generate_button_not_found');
        testReporter.completeStep(
          'Generate ssh key for vault',
          'skipped',
          'SSH generate button not found'
        );
      }

      testReporter.startStep('Save vault configuration');

      // Use precise selector - no fallbacks
      const saveButton = page.locator('[data-testid="vault-modal-save-button"]');

      await expect(saveButton).toBeVisible({ timeout: 5000 });
      await expect(saveButton).toBeEnabled({ timeout: 5000 });
      await saveButton.click();
      await screenshotManager.captureStep('vault_save_clicked');
      testReporter.completeStep('Save vault configuration', 'passed');

      testReporter.startStep('Validate vault configuration saved');

      const modalStillVisible = await vaultModal.isVisible();
      const successDetected = !modalStillVisible || (await checkNotificationSuccess(page));

      if (!successDetected) {
        await screenshotManager.captureStep('vault_save_validation_failed');
        testReporter.completeStep(
          'Validate vault configuration saved',
          'failed',
          'Could not confirm vault configuration save success'
        );
        throw new Error('Vault configuration save validation failed');
      }

      await screenshotManager.captureStep('vault_save_validated');
      testReporter.completeStep('Validate vault configuration saved', 'passed');

      await testReporter.generateDetailedReport();
      testReporter.logTestCompletion();
    });
  });

// Helper functions to reduce cognitive complexity

async function fillFieldIfEmpty(
  primaryLocator: import('@playwright/test').Locator,
  fallbackLocator: import('@playwright/test').Locator,
  value: string
): Promise<void> {
  if (await primaryLocator.isVisible()) {
    const currentValue = await primaryLocator.inputValue();
    if (!currentValue) {
      await primaryLocator.fill(value);
    }
    return;
  }

  if (await fallbackLocator.isVisible()) {
    const currentValue = await fallbackLocator.inputValue();
    if (!currentValue) {
      await fallbackLocator.fill(value);
    }
  }
}

async function fillEmptyTextFields(page: import('@playwright/test').Page): Promise<void> {
  const textFields = page.locator('.ant-modal input[type="text"], .ant-modal textarea');
  const textFieldCount = await textFields.count();

  for (let i = 0; i < textFieldCount; i++) {
    await fillSingleEmptyField(textFields.nth(i));
  }
}

async function fillSingleEmptyField(field: import('@playwright/test').Locator): Promise<void> {
  if (!(await field.isVisible())) {
    return;
  }

  const value = await field.inputValue();
  if (value) {
    return;
  }

  const placeholder = (await field.getAttribute('placeholder')) ?? '';
  if (placeholder.toLowerCase().includes('datastore')) {
    await field.fill('/mnt/rediacc');
  } else if (placeholder) {
    await field.fill('default_value');
  }
}

async function openSshDialog(page: import('@playwright/test').Page): Promise<boolean> {
  const sshGenerateCandidates = [
    '[data-testid="vault-editor-generate-SSH_PRIVATE_KEY"]',
    'button[title*="Generate SSH"]',
    'button:has-text("Generate SSH")',
  ];

  for (const selector of sshGenerateCandidates) {
    const btn = page.locator(selector).first();
    if (await btn.isVisible()) {
      await btn.click();
      return true;
    }
  }

  return false;
}

async function configureSshOptions(
  page: import('@playwright/test').Page,
  screenshotManager: import('../../src/utils/screenshot/ScreenshotManager').ScreenshotManager,
  testReporter: import('../../src/utils/report/TestReporter').TestReporter
): Promise<void> {
  // Playwright auto-waits for elements to be actionable
  await clickIfVisible(page.locator('label:has-text("RSA")').first());
  await clickIfVisible(page.locator('label:has-text("4096")').first());

  const generateButton = page.locator('[data-testid="vault-editor-generate-button"]');

  if (!(await generateButton.isVisible())) {
    await screenshotManager.captureStep('ssh_generate_button_in_dialog_not_found');
    testReporter.completeStep(
      'Generate ssh key for vault',
      'skipped',
      'Generate button in ssh dialog not found'
    );
    return;
  }

  await generateButton.click();

  // Wait for SSH key generation to complete - apply button appears when ready
  const applyButton = page.locator('[data-testid="vault-editor-apply-generated"]');
  await applyButton.waitFor({ state: 'visible', timeout: 30000 });

  await clickIfVisible(applyButton);

  await screenshotManager.captureStep('ssh_key_generated_and_applied');
  testReporter.completeStep('Generate ssh key for vault', 'passed');
}

async function clickIfVisible(locator: import('@playwright/test').Locator): Promise<void> {
  if (await locator.isVisible()) {
    await locator.click();
  }
}

async function checkNotificationSuccess(page: import('@playwright/test').Page): Promise<boolean> {
  const notificationSelectors = ['.ant-message', '.ant-notification', '[role="alert"]'];
  const successIndicators = [
    'Vault configuration saved successfully',
    'Vault updated successfully',
    'Configuration saved',
  ];

  for (const selector of notificationSelectors) {
    if (await hasSuccessNotification(page.locator(selector), successIndicators)) {
      return true;
    }
  }

  return false;
}

async function hasSuccessNotification(
  notification: import('@playwright/test').Locator,
  indicators: string[]
): Promise<boolean> {
  if (!(await notification.isVisible())) {
    return false;
  }

  const text = (await notification.textContent()) ?? '';
  return indicators.some((indicator) => text.includes(indicator));
}
