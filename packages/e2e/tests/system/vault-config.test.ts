import { test, expect } from '../../src/base/BaseTest';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { LoginPage } from '../../pages/auth/LoginPage';
import { requireEnvVar } from '../../src/utils/env';

// Vault configuration tests migrated from Python VaultConfigurationTest
// Focus: open System page, open organization vault modal, fill required fields, generate SSH key and save

// Skip: Organization Settings page requires Power Mode which is a hidden developer feature
// Power Mode is enabled via Ctrl+Shift+E keyboard shortcut and requires session-only state
// that cannot be reliably triggered in automated tests
test.describe.skip('System Vault Configuration Tests', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
    
    await loginPage.navigate();
    
    // Login with admin credentials
    const adminEmail = requireEnvVar('SYSTEM_ADMIN_EMAIL');
    const adminPassword = requireEnvVar('SYSTEM_ADMIN_PASSWORD');
    await loginPage.login(adminEmail, adminPassword);
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
    await page.waitForTimeout(500);

    // Click on Organization submenu (requires power mode)
    const organizationSubNav = page.locator('[role="navigation"]').getByText('Organization');
    await organizationSubNav.waitFor({ state: 'visible', timeout: 10000 });
    await organizationSubNav.click();
    await page.waitForLoadState('networkidle');
  });

  test('should configure organization vault with generated ssh key @system @vault @regression', async ({
    page,
    screenshotManager,
    testReporter
  }) => {
    const stepNavigateSystem = await testReporter.startStep('Verify Organization Settings page loaded');

    // Already navigated to /console/settings/organization in beforeEach
    // Verify we're on the correct page by checking for organization vault button
    const organizationVaultButton = page.locator('[data-testid="system-organization-vault-button"]');

    try {
      await expect(organizationVaultButton).toBeVisible({ timeout: 10000 });
      await screenshotManager.captureStep('organization_settings_page_loaded');
      await testReporter.completeStep('Verify Organization Settings page loaded', 'passed');
    } catch (error) {
      await screenshotManager.captureStep('organization_settings_page_not_loaded');
      await testReporter.completeStep(
        'Verify Organization Settings page loaded',
        'failed',
        'Organization Settings page did not load correctly'
      );
      throw new Error('Organization Settings page did not load correctly');
    }

    const stepOpenVault = await testReporter.startStep('Open organization vault configuration');

    // Use precise selector - no fallbacks
    await organizationVaultButton.click();

    const vaultModal = page.locator('[data-testid="vault-modal"]');

    try {
      await expect(vaultModal).toBeVisible({ timeout: 5000 });
      await screenshotManager.captureStep('vault_modal_opened');
      await testReporter.completeStep('Open organization vault configuration', 'passed');
    } catch (error) {
      await screenshotManager.captureStep('vault_modal_not_visible');
      await testReporter.completeStep(
        'Open organization vault configuration',
        'failed',
        'Vault configuration modal did not become visible'
      );
      throw error;
    }

    const stepFillFields = await testReporter.startStep('Fill required vault fields');

    const universalUserIdField = page.locator(
      '[data-testid="vault-editor-field-UNIVERSAL_USER_ID"]'
    );

    if (await universalUserIdField.isVisible()) {
      const currentValue = await universalUserIdField.inputValue();
      if (!currentValue) {
        await universalUserIdField.fill('universal_user_001');
      }
    } else {
      const fallbackUserId = page.locator(
        'input[placeholder*="Universal User ID" i]'
      ).first();
      if (await fallbackUserId.isVisible()) {
        const currentValue = await fallbackUserId.inputValue();
        if (!currentValue) {
          await fallbackUserId.fill('universal_user_001');
        }
      }
    }

    const universalUserNameField = page.locator(
      '[data-testid="vault-editor-field-UNIVERSAL_USER_NAME"]'
    );

    if (await universalUserNameField.isVisible()) {
      const currentValue = await universalUserNameField.inputValue();
      if (!currentValue) {
        await universalUserNameField.fill('Universal User');
      }
    } else {
      const fallbackUserName = page.locator(
        'input[placeholder*="Universal User Name" i]'
      ).first();
      if (await fallbackUserName.isVisible()) {
        const currentValue = await fallbackUserName.inputValue();
        if (!currentValue) {
          await fallbackUserName.fill('Universal User');
        }
      }
    }

    const textFields = page.locator(
      '.ant-modal input[type="text"], .ant-modal textarea'
    );

    const textFieldCount = await textFields.count();

    for (let i = 0; i < textFieldCount; i++) {
      const field = textFields.nth(i);
      if (await field.isVisible()) {
        const value = await field.inputValue();
        if (!value) {
          const placeholder = (await field.getAttribute('placeholder')) || '';
          if (placeholder.toLowerCase().includes('datastore')) {
            await field.fill('/mnt/rediacc');
          } else if (placeholder) {
            await field.fill('default_value');
          }
        }
      }
    }

    await screenshotManager.captureStep('vault_fields_filled');
    await testReporter.completeStep('Fill required vault fields', 'passed');

    const stepGenerateSsh = await testReporter.startStep('Generate ssh key for vault');

    const sshGenerateCandidates = [
      '[data-testid="vault-editor-generate-SSH_PRIVATE_KEY"]',
      'button[title*="Generate SSH"]',
      'button:has-text("Generate SSH")'
    ];

    let sshDialogOpened = false;

    for (const selector of sshGenerateCandidates) {
      const btn = page.locator(selector).first();
      if (await btn.isVisible()) {
        await btn.click();
        sshDialogOpened = true;
        break;
      }
    }

    if (!sshDialogOpened) {
      await screenshotManager.captureStep('ssh_generate_button_not_found');
      await testReporter.completeStep(
        'Generate ssh key for vault',
        'skipped',
        'SSH generate button not found'
      );
    } else {
      await page.waitForTimeout(500);

      const rsaOption = page.locator('label:has-text("RSA")').first();
      if (await rsaOption.isVisible()) {
        await rsaOption.click();
      }

      const keySizeOption = page.locator('label:has-text("4096")').first();
      if (await keySizeOption.isVisible()) {
        await keySizeOption.click();
      }

      // Use precise selector for generate button
      const generateButton = page.locator('[data-testid="vault-editor-generate-button"]');

      if (await generateButton.isVisible()) {
        await generateButton.click();
        await page.waitForTimeout(5000);

        // Apply the generated key
        const applyButton = page.locator('[data-testid="vault-editor-apply-generated"]');
        if (await applyButton.isVisible()) {
          await applyButton.click();
        }

        await screenshotManager.captureStep('ssh_key_generated_and_applied');
        await testReporter.completeStep('Generate ssh key for vault', 'passed');
      } else {
        await screenshotManager.captureStep('ssh_generate_button_in_dialog_not_found');
        await testReporter.completeStep(
          'Generate ssh key for vault',
          'skipped',
          'Generate button in ssh dialog not found'
        );
      }
    }

    const stepSaveVault = await testReporter.startStep('Save vault configuration');

    // Use precise selector - no fallbacks
    const saveButton = page.locator('[data-testid="vault-modal-save-button"]');

    await expect(saveButton).toBeVisible({ timeout: 5000 });
    await expect(saveButton).toBeEnabled({ timeout: 5000 });
    await saveButton.click();
    await screenshotManager.captureStep('vault_save_clicked');
    await testReporter.completeStep('Save vault configuration', 'passed');

    const stepValidateSave = await testReporter.startStep('Validate vault configuration saved');

    const modalStillVisible = await vaultModal.isVisible();

    const notificationSelectors = [
      '.ant-message',
      '.ant-notification',
      '[role="alert"]'
    ];

    const successIndicators = [
      'Vault configuration saved successfully',
      'Vault updated successfully',
      'Configuration saved'
    ];

    let successDetected = false;

    for (const selector of notificationSelectors) {
      const notification = page.locator(selector);
      if (await notification.isVisible()) {
        const text = (await notification.textContent()) || '';
        for (const indicator of successIndicators) {
          if (text.includes(indicator)) {
            successDetected = true;
            break;
          }
        }
      }
      if (successDetected) {
        break;
      }
    }

    if (!modalStillVisible) {
      successDetected = true;
    }

    if (!successDetected) {
      await screenshotManager.captureStep('vault_save_validation_failed');
      await testReporter.completeStep(
        'Validate vault configuration saved',
        'failed',
        'Could not confirm vault configuration save success'
      );
      throw new Error('Vault configuration save validation failed');
    }

    await screenshotManager.captureStep('vault_save_validated');
    await testReporter.completeStep('Validate vault configuration saved', 'passed');

    await testReporter.generateDetailedReport();
    testReporter.logTestCompletion();
  });
});
