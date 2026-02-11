import { test } from '@/base/BaseTest';
import { LoginPage } from '@/pages/auth/LoginPage';

test.describe('Login Tests - Registration Navigation', () => {
    let loginPage: LoginPage;

    test.beforeEach(({ page }) => {
        loginPage = new LoginPage(page);
    });

    test('should navigate to registration page @auth', async ({ page, testReporter }) => {
        testReporter.startStep('Navigate to login page');
        await loginPage.navigate();
        testReporter.completeStep('Navigate to login page', 'passed');

        testReporter.startStep('Click register link');

        await loginPage.clickRegister();

        // Wait for registration form to appear
        await page
            .locator('[data-testid="registration-organization-input"]')
            .waitFor({ state: 'visible' });

        testReporter.completeStep('Click register link', 'passed');

        await testReporter.finalizeTest();
    });
});
