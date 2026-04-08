import { test, expect } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';
import { type Page } from '@playwright/test';

/**
 * Common helper to navigate to the credentials page and open the creation modal.
 */
async function navigateToCredentialCreation(page: Page) {
  await page.getByTestId('user-menu-button').click();
  await page
    .getByTestId('main-mode-toggle')
    .locator('.ant-segmented-item', { hasText: /Expert|Uzman/i })
    .click();
  await page.getByTestId('user-menu-button').click();

  const credentialsNavItem = page.locator(
    '[data-testid="main-nav-credentials"][href="/console/credentials"]'
  );
  await expect(credentialsNavItem).toBeVisible();
  await credentialsNavItem.click();

  await page.getByTestId('resources-create-repositorie-button').click();
}

/**
 * Common helper to create a credential configuration in the UI.
 */
async function fillAndSubmitCredentialForm(page: Page, repositoryName: string, guid: string) {
  await page.evaluate(() => {
    const banner = document.querySelector('[data-testid="preview-warning-banner"]');
    if (banner) banner.remove();
  });

  const teamSelect = page.getByTestId('resource-modal-field-teamName-select');
  await teamSelect.click();
  await page.locator('.ant-select-item-option').first().click();

  await page.getByTestId('resource-modal-field-repositoryName-input').fill(repositoryName);
  await page.getByTestId('resource-modal-field-repositoryGuid-input').fill(guid);

  await page.getByTestId('vault-editor-field-credential').fill('uH$xX#wA(|qMq&yw)pmjvZ5HT9s+rrYs');

  await page.getByTestId('resource-modal-ok-button').click();
}

test.describe('Credential Management', () => {
  let dashboardPage: DashboardPage;
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);

    await loginPage.navigate();
    await loginPage.performQuickLogin();
    await dashboardPage.waitForNetworkIdle();
  });

  test('02-09-02-01-credential-trace - should trace a credential configuration', async ({
    page,
    testReporter,
  }) => {
    const random4 = Math.floor(1000 + Math.random() * 9000);
    const guid = `550e8400-e29b-41d4-a716-44665544${random4}`;
    const repositoryName = `CREDENTIALS SQL SERVER BACKUP${random4}`;

    test.setTimeout(90000);
    testReporter.startStep('Navigate and open storage creation form');

    await navigateToCredentialCreation(page);

    testReporter.completeStep('Navigate and open credential form', 'passed');
    testReporter.startStep('Fill credential form');

    await fillAndSubmitCredentialForm(page, repositoryName, guid);

    testReporter.completeStep('Fill credential form', 'passed');
    testReporter.startStep('Verify credential creation');

    // Verify credential exists using test-id to avoid notification banner collision
    await expect(page.getByTestId(`resource-list-item-${guid}`)).toBeVisible({ timeout: 15000 });

    const editButton = page.getByTestId(`resources-repository-edit-${guid}`);
    await expect(editButton).toBeVisible({ timeout: 15000 });
    await editButton.click();

    const repositoryNameInput = page.getByTestId('resource-modal-field-repositoryName-input');
    const currentValue = await repositoryNameInput.inputValue();

    const newValue = currentValue.slice(0, -4);
    await repositoryNameInput.fill(newValue);

    await page.getByTestId('resource-modal-ok-button').click();

    const traceButton = page.getByTestId(`resources-repository-trace-${guid}`);
    await expect(traceButton).toBeVisible({ timeout: 15000 });
    await traceButton.click();

    testReporter.startStep('Click export button in audit trace dropdown');

    const exportButton = page.getByTestId('audit-trace-export-button');
    await expect(exportButton).toBeVisible({ timeout: 10000 });
    await exportButton.click();

    testReporter.completeStep('Click export button in audit trace dropdown', 'passed');
    testReporter.completeStep('Verify credential creation, edit and trace', 'passed');
    await testReporter.finalizeTest();
  });
});
