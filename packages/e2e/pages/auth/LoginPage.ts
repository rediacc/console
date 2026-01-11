import { Page, Locator } from '@playwright/test';
import { BasePage } from '../../src/base/BasePage';
import { requireEnvVar } from '../../src/utils/env';

export class LoginPage extends BasePage {
  private readonly emailInput: Locator;
  private readonly passwordInput: Locator;
  private readonly loginButton: Locator;
  private readonly forgotPasswordLink: Locator;
  private readonly registerLink: Locator;
  private readonly errorMessage: Locator;
  private readonly loadingSpinner: Locator;
  private readonly registrationOrganizationInput: Locator;
  private readonly registrationEmailInput: Locator;
  private readonly registrationPasswordInput: Locator;
  private readonly registrationPasswordConfirmInput: Locator;
  private readonly registrationTermsCheckbox: Locator;
  private readonly registrationSubmitButton: Locator;
  private readonly registrationActivationCodeInput: Locator;
  private readonly registrationVerifyButton: Locator;

  constructor(page: Page) {
    super(page, '/console/login');

    this.emailInput = page.locator('[data-testid="login-email-input"]');
    this.passwordInput = page.locator('[data-testid="login-password-input"]');
    this.loginButton = page.locator('[data-testid="login-submit-button"]');
    this.forgotPasswordLink = page.locator('[data-testid="forgot-password"]');
    this.registerLink = page.locator('[data-testid="login-register-link"]');
    this.errorMessage = page.locator('[data-testid="login-error-alert"]');
    this.loadingSpinner = page.locator('.ant-spin');
    this.registrationOrganizationInput = page.locator('[data-testid="registration-organization-input"]');
    this.registrationEmailInput = page.locator('[data-testid="registration-email-input"]');
    this.registrationPasswordInput = page.locator('[data-testid="registration-password-input"]');
    this.registrationPasswordConfirmInput = page.locator('[data-testid="registration-password-confirm-input"]');
    this.registrationTermsCheckbox = page.locator('#termsAccepted');
    this.registrationSubmitButton = page.locator('[data-testid="registration-submit-button"]');
    this.registrationActivationCodeInput = page.locator('[data-testid="registration-activation-code-input"]');
    this.registrationVerifyButton = page.locator('[data-testid="registration-verify-button"]');
  }

  getPageLocators(): Record<string, Locator> {
    return {
      emailInput: this.emailInput,
      passwordInput: this.passwordInput,
      loginButton: this.loginButton,
      forgotPasswordLink: this.forgotPasswordLink,
      registerLink: this.registerLink,
      errorMessage: this.errorMessage,
      loadingSpinner: this.loadingSpinner,
      registrationOrganizationInput: this.registrationOrganizationInput,
      registrationEmailInput: this.registrationEmailInput,
      registrationPasswordInput: this.registrationPasswordInput,
      registrationPasswordConfirmInput: this.registrationPasswordConfirmInput,
      registrationTermsCheckbox: this.registrationTermsCheckbox,
      registrationSubmitButton: this.registrationSubmitButton,
      registrationActivationCodeInput: this.registrationActivationCodeInput,
      registrationVerifyButton: this.registrationVerifyButton
    };
  }

  async login(email: string, password: string): Promise<void> {
    console.log(`   @ Logging in with email: ${email}`);
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.loginButton.click();
    await this.waitForNetworkIdle();
  }

  async loginWithValidation(email: string, password: string): Promise<void> {
    await this.verifyElementVisible(this.emailInput);
    await this.verifyElementVisible(this.passwordInput);
    await this.verifyElementVisible(this.loginButton);
    
    await this.login(email, password);
  }

  async waitForLoginCompletion(): Promise<void> {
    await this.waitForElementToDisappear(this.loadingSpinner, 10000);
    await this.page.waitForURL('**/machines', { timeout: 30000 });
  }

  async getErrorMessage(): Promise<string> {
    await this.waitForElement(this.errorMessage);
    return await this.errorMessage.textContent() || '';
  }

  async validateErrorMessage(expectedMessage?: string): Promise<boolean> {
    try {
      await this.waitForElement(this.errorMessage, 5000);
      const actualMessage = await this.errorMessage.textContent() || '';
      
      if (expectedMessage) {
        return actualMessage.includes(expectedMessage);
      }
      
      return actualMessage.length > 0;
    } catch {
      return false;
    }
  }

  async isLoginButtonEnabled(): Promise<boolean> {
    return await this.loginButton.isEnabled();
  }

  async clickForgotPassword(): Promise<void> {
    await this.forgotPasswordLink.click();
  }

  async clickRegister(): Promise<void> {
    await this.registerLink.click();
  }

  async clearForm(): Promise<void> {
    await this.emailInput.clear();
    await this.passwordInput.clear();
  }

  async fillEmailOnly(email: string): Promise<void> {
    await this.emailInput.fill(email);
  }

  async fillPasswordOnly(password: string): Promise<void> {
    await this.passwordInput.fill(password);
  }

  async verifyFormValidation(): Promise<void> {
    await this.verifyElementVisible(this.emailInput);
    await this.verifyElementVisible(this.passwordInput);
    await this.verifyElementEnabled(this.loginButton);
  }

  async performQuickLogin(): Promise<void> {
    const email = requireEnvVar('TEST_USER_EMAIL');
    const password = requireEnvVar('TEST_USER_PASSWORD');
    
    console.log('   🔐 Performing authentication...');
    await this.login(email, password);
    await this.waitForLoginCompletion();
    console.log('   ✅ Authentication successful');
  }

  async fillRegistrationForm(
    organizationName: string,
    email: string,
    password: string,
    passwordConfirm: string,
    acceptTerms: boolean = true
  ): Promise<void> {
    await this.registrationOrganizationInput.fill(organizationName);
    await this.registrationEmailInput.fill(email);
    await this.registrationPasswordInput.fill(password);
    await this.registrationPasswordConfirmInput.fill(passwordConfirm);

    if (acceptTerms) {
      if (!(await this.registrationTermsCheckbox.isChecked())) {
        await this.registrationTermsCheckbox.check();
      }
    }
  }

  async submitRegistrationForm(): Promise<void> {
    await this.registrationSubmitButton.click();
    await this.waitForNetworkIdle();
  }

  async completeRegistration(
    organizationName: string,
    email: string,
    password: string,
    passwordConfirm: string,
    acceptTerms: boolean = true
  ): Promise<void> {
    await this.fillRegistrationForm(organizationName, email, password, passwordConfirm, acceptTerms);
    await this.submitRegistrationForm();
  }

  async completeRegistrationVerification(code: string = '11111'): Promise<void> {
    await this.registrationActivationCodeInput.fill(code);
    await this.registrationVerifyButton.click();
    await this.waitForNetworkIdle();
  }
}