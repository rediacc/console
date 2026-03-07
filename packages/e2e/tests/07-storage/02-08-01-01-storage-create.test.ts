import { test, expect } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';

test.describe('Storage Management', () => {
    let dashboardPage: DashboardPage;
    let loginPage: LoginPage;

    test.beforeEach(async ({ page }) => {
        loginPage = new LoginPage(page);
        dashboardPage = new DashboardPage(page);

        await loginPage.navigate();
        await loginPage.performQuickLogin();
        await dashboardPage.waitForNetworkIdle();
    });

    test('02-08-01-01-storage-create - should create a new storage configuration', async ({
        page,
        testReporter,
    }) => {
        test.setTimeout(90000);
        testReporter.startStep('Navigate and open storage creation form');

        // 3- user-menu-button click and select "Expert/Uzman" mode
        await page.getByTestId('user-menu-button').click();
        await page.getByTestId('main-mode-toggle').locator('.ant-segmented-item', { hasText: /Expert|Uzman/i }).click();

        // Mod seçildikten sonra menünün kapanması için tekrar menü butonuna tıklıyoruz
        await page.getByTestId('user-menu-button').click();

        // 4- data-testid="main-nav-storage" ve href="/console/storage" exist check
        const storageNavItem = page.locator('[data-testid="main-nav-storage"][href="/console/storage"]');
        await expect(storageNavItem).toBeVisible();

        // 5- data-testid="main-nav-storage" ve href="/console/storage" click
        await storageNavItem.click();

        // 6- data-testid="resources-create-storage-button" click
        await page.getByTestId('resources-create-storage-button').click();

        testReporter.completeStep('Navigate and open storage creation form', 'passed');
        testReporter.startStep('Fill storage creation form');
        await page.evaluate(() => {
            const banner = document.querySelector('[data-testid="preview-warning-banner"]');
            if (banner) banner.remove();
        });

        // 7- data-testid="resource-modal-field-teamName-select" click and select 1st
        const teamSelect = page.getByTestId('resource-modal-field-teamName-select');
        await teamSelect.click();
        // Assuming it's an Ant Design select, we might need to click the first option in the dropdown
        await page.locator('.ant-select-item-option').first().click();


        // 8- data-testid="resource-modal-field-storageName-input" -> "SQL SERVER YEDEK"
        await page.getByTestId('resource-modal-field-storageName-input').fill('SQL SERVER YEDEK');

        // 9- data-testid="vault-editor-field-description" -> "SQL SERVER YEDEK"
        await page.getByTestId('vault-editor-field-description').fill('SQL SERVER YEDEK');

        // 10- data-testid="vault-editor-field-provider" click and select "drive"
        const providerSelect = page.getByTestId('vault-editor-field-provider');
        await providerSelect.click();
        await page.locator('.ant-select-item-option').getByText('drive', { exact: true }).click();

        // 11- data-testid="vault-editor-field-token-new-key" -> "Test12345678"
        await page.getByTestId('vault-editor-field-token-new-key').fill('Test12345678');

        // 12- data-testid="vault-editor-field-token-add" click
        await page.getByTestId('vault-editor-field-token-add').click({ force: true });

        // 13- data-testid="resource-modal-ok-button" click
        await page.getByTestId('resource-modal-ok-button').click({ force: true });

        testReporter.completeStep('Fill storage creation form', 'passed');
        testReporter.startStep('Verify storage creation');

        // 14- Verify "SQL SERVER YEDEK" exists on the page
        await expect(page.getByText('SQL SERVER YEDEK')).toBeVisible({ timeout: 15000 });

        testReporter.completeStep('Verify storage creation', 'passed');
        await testReporter.finalizeTest();
    });
});
