import { test, expect } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';

test.describe('Language Selection Tests', () => {
    let dashboardPage: DashboardPage;
    let loginPage: LoginPage;

    test.beforeEach(async ({ page }) => {
        loginPage = new LoginPage(page);
        dashboardPage = new DashboardPage(page);

        await loginPage.navigate();
        await loginPage.performQuickLogin();
        await dashboardPage.waitForNetworkIdle();
    });

    test('should change language to Turkish @system @language @regression', async ({
        page,
        testReporter,
    }) => {
        test.setTimeout(60000);
        testReporter.startStep('Open User Menu');

        // Click the user menu button
        const userMenuButton = page.getByTestId('user-menu-button');
        await expect(userMenuButton).toBeVisible();
        await userMenuButton.click();

        testReporter.completeStep('Open User Menu', 'passed');
        testReporter.startStep('Change language to Turkish');

        // Locate the language selector
        const languageSelector = page.getByTestId('language-selector');
        await expect(languageSelector).toBeVisible();
        await languageSelector.click();

        // Select Turkish from the dropdown
        // Based on LanguageSelector/index.tsx, the options have labels with flag and name
        const turkishOption = page.locator('.ant-select-item-option-content').filter({ hasText: '🇹🇷 Türkçe' });
        await expect(turkishOption).toBeVisible();
        await turkishOption.click();

        testReporter.completeStep('Change language to Turkish', 'passed');
        testReporter.startStep('Verify language changed to Turkish');

        // Verify by checking if labels changed to Turkish
        // "Interface Mode" becomes "Arayüz Modu" in common.json
        const uiModeLabel = page.getByText('Ayarlar');
        await expect(uiModeLabel).toBeVisible({ timeout: 10000 });



        testReporter.completeStep('Verify language changed to Turkish', 'passed');
        await testReporter.finalizeTest();
    });
});
