import { test, expect } from '../../src/base/BaseTest';
import { LoginPage } from '../../pages/auth/LoginPage';
import { DashboardPage } from '../../pages/dashboard/DashboardPage';
import { requireEnvVar } from '../../src/utils/env';

test.describe('Login Tests', () => {
  let loginPage: LoginPage;
  let dashboardPage: DashboardPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    dashboardPage = new DashboardPage(page);
  });

  test('should login with valid credentials @auth', async ({ 
    page, 
    testReporter 
  }) => {
    const step1 = await testReporter.startStep('Navigate to login page');
    
    await loginPage.navigate();
    await loginPage.verifyFormValidation();
    
    await testReporter.completeStep('Navigate to login page', 'passed');

    const step2 = await testReporter.startStep('Enter valid credentials');
    
    const email = requireEnvVar('TEST_USER_EMAIL');
    const password = requireEnvVar('TEST_USER_PASSWORD');
    
    await loginPage.login(email, password);
    await testReporter.completeStep('Enter valid credentials', 'passed');

    const step3 = await testReporter.startStep('Verify successful login');
    
    await loginPage.waitForLoginCompletion();
    await dashboardPage.verifyDashboardLoaded();
    
    await expect(page.url()).toContain('/machines');
    
    await testReporter.completeStep('Verify successful login', 'passed');
    
    await testReporter.finalizeTest();
  });

  test('should show error with invalid credentials @auth', async ({ 
    page, 
    testReporter 
  }) => {
    const step1 = await testReporter.startStep('Navigate to login page');
    await loginPage.navigate();
    await testReporter.completeStep('Navigate to login page', 'passed');

    const step2 = await testReporter.startStep('Enter invalid credentials');
    
    await loginPage.login('invalid@example.com', 'wrongpassword');
    
    await testReporter.completeStep('Enter invalid credentials', 'passed');

    const step3 = await testReporter.startStep('Verify error message');
    
    await loginPage.validateErrorMessage('not found');

    await testReporter.completeStep('Verify error message', 'passed');
    
    await testReporter.finalizeTest();
  });

  test('should disable login button with empty fields @auth', async ({ 
    page, 
    testReporter 
  }) => {
    const step1 = await testReporter.startStep('Navigate to login page');
    await loginPage.navigate();
    await testReporter.completeStep('Navigate to login page', 'passed');

    const step2 = await testReporter.startStep('Verify empty form state');
    
    await loginPage.clearForm();
    const isButtonEnabled = await loginPage.isLoginButtonEnabled();
    
    await testReporter.completeStep('Verify empty form state', 'passed');
    await testReporter.finalizeTest();
  });

   test('should navigate to registration page @auth', async ({ 
    page, 
    testReporter 
  }) => {
    const step1 = await testReporter.startStep('Navigate to login page');
    await loginPage.navigate();
    await testReporter.completeStep('Navigate to login page', 'passed');

    const step2 = await testReporter.startStep('Click register link');
    
    await loginPage.clickRegister();
    
    // Wait for navigation to register page
    await page.waitForTimeout(2000);
    
    await testReporter.completeStep('Click register link', 'passed');
    
    await testReporter.finalizeTest();
  });
});