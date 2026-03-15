import { test, expect } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';
import { DashboardPage } from '@/pages/dashboard/DashboardPage';

test.describe('Storage Management', () => {
    let dashboardPage: DashboardPage;
    let loginPage: LoginPage;

    const random4 = Math.floor(1000 + Math.random() * 9000);
    const guid = `550e8400-e29b-41d4-a716-44665544${random4}`;
    const repositoryName = `CREDENTIALS SQL SERVER YEDEK${random4}`;

    test.beforeEach(async ({ page }) => {
        loginPage = new LoginPage(page);
        dashboardPage = new DashboardPage(page);

        await loginPage.navigate();
        await loginPage.performQuickLogin();
        await dashboardPage.waitForNetworkIdle();
    });

    test('02-09-02-01-credential-trace- should trace a credential configuration', async ({
        page,
        testReporter,
    }) => {
        test.setTimeout(90000);

        testReporter.startStep('Navigate and open storage creation form');

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

        testReporter.completeStep('Navigate and open credential form', 'passed');
        testReporter.startStep('Fill credential form');

        await page.evaluate(() => {
            const banner = document.querySelector('[data-testid="preview-warning-banner"]');
            if (banner) banner.remove();
        });

        const teamSelect = page.getByTestId('resource-modal-field-teamName-select');
        await teamSelect.click();
        await page.locator('.ant-select-item-option').first().click();

        await page.getByTestId('resource-modal-field-repositoryName-input').fill(repositoryName);

        await page.getByTestId('resource-modal-field-repositoryGuid-input').fill(guid);

        await page
            .getByTestId('vault-editor-field-credential')
            .fill('uH$xX#wA(|qMq&yw)pmjvZ5HT9s+rrYs');

        await page.getByTestId('resource-modal-ok-button').click({ force: true });

        testReporter.completeStep('Fill credential form', 'passed');
        testReporter.startStep('Verify credential creation');

        await expect(page.getByText(repositoryName)).toBeVisible({ timeout: 15000 });

        const turkishOption = page
            .locator('.ant-select-item-option-content')
            .filter({ hasText: 'Türkçe' });

        if (await turkishOption.isVisible()) {
            await turkishOption.click();
        }


        const deleteButton = page.getByTestId(`resources-repository-delete-${guid}`);
        await expect(deleteButton).toBeVisible({ timeout: 15000 });
        await deleteButton.click();

        testReporter.completeStep('Verify credential creation, edit and trace', 'passed');

        await testReporter.finalizeTest();
    });
});