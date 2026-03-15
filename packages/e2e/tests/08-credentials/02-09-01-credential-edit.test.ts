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
    const random4 = Math.floor(1000 + Math.random() * 9000); // 4 haneli random sayı
    test('02-09-01-01-credential-edit- should create a new storage configuration', async ({
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

        // 4- data-testid="main-nav-storage" ve href="/console/credentials" exist check
        const credentialsNavItem = page.locator('[data-testid="main-nav-credentials"][href="/console/credentials"]');
        await expect(credentialsNavItem).toBeVisible();

        // 5- data-testid="main-nav-credentials" ve href="/console/credentials" click
        await credentialsNavItem.click();
        // 6- data-testid="resources-create-repositorie-button" click
        // Note: The user provided data-testid="data-testid="resources-create-repositorie-button"" which looks like a typo, I will use "resources-create-repositorie-button"
        await page.getByTestId('resources-create-repositorie-button').click();

        testReporter.completeStep('Navigate and open credential form', 'passed');
        testReporter.startStep('Fill credential form');
        //BANNERİ KAPATMA KODU
        await page.evaluate(() => {
            const banner = document.querySelector('[data-testid="preview-warning-banner"]');
            if (banner) banner.remove();
        });


        // 7- data-testid="resource-modal-field-teamName-select" click and select 1st
        const teamSelect = page.getByTestId('resource-modal-field-teamName-select');
        await teamSelect.click();
        await page.locator('.ant-select-item-option').first().click();

        // 8- data-testid="resource-modal-field-repositoryName-input" -> "CREDENTIALS SQL SERVER YEDEK"
        await page.getByTestId('resource-modal-field-repositoryName-input').fill('CREDENTIALS SQL SERVER YEDEK' + random4);

        // 9- data-testid="resource-modal-field-repositoryGuid-input" -> "550e8400-e29b-41d4-a716-446655440000"
        // Note: The user provided data-testid="data-testid="resource-modal-field-repositoryGuid-input""
        await page.getByTestId('resource-modal-field-repositoryGuid-input').fill('550e8400-e29b-41d4-a716-44665544' + random4);

        // 10- data-testid="vault-editor-field-credential" -> "uH$xX#wA(|qMq&yw)pmjvZ5HT9s+rrYs"
        await page.getByTestId('vault-editor-field-credential').fill('uH$xX#wA(|qMq&yw)pmjvZ5HT9s+rrYs');

        // 11- data-testid="resource-modal-ok-button" click
        await page.getByTestId('resource-modal-ok-button').click({ force: true });

        testReporter.completeStep('Fill credential form', 'passed');
        testReporter.startStep('Verify credential creation and change language');

        // 12-14- Verify "CREDENTIALS SQL SERVER YEDEK" exists on the page
        await expect(page.getByText('CREDENTIALS SQL SERVER YEDEK')).toBeVisible({ timeout: 15000 });

        // Language selection in dialog: "Türkçe"
        // Assuming a dialog or language selector is open
        const turkishOption = page.locator('.ant-select-item-option-content').filter({ hasText: 'Türkçe' });
        if (await turkishOption.isVisible()) {
            await turkishOption.click();
        }

        // 15- data-testid="resources-repository-edit-550e8400-e29b-41d4-a716-44665544" + random4 click
        await page.locator(`[data-testid="resources-repository-edit-550e8400-e29b-41d4-a716-44665544${random4}"].ant-btn.ant-btn-circle.ant-btn-primary`).click();

        // 16- Get value from "resource-modal-field-repositoryName-input", remove last 3 chars and click OK
        const repositoryNameInput = page.getByTestId('resource-modal-field-repositoryName-input');
        const currentValue = await repositoryNameInput.inputValue();
        const newValue = currentValue.slice(0, -3);
        await repositoryNameInput.fill(newValue);

        await page.getByTestId('resource-modal-ok-button').click({ force: true });

        testReporter.completeStep('Verify credential creation and change language', 'passed');
        await testReporter.finalizeTest();
    });
});
