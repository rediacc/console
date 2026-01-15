import { Page, Locator } from '@playwright/test';
import { BasePage } from '../../src/base/BasePage';
import { loadGlobalState } from '../../src/setup/global-state';
import { getEnvVarWithDefault } from '../../src/utils/env';

export class LoginPage extends BasePage {
  private readonly emailInput: Locator;
  private readonly passwordInput: Locator;
  private readonly loginButton: Locator;
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
    this.registerLink = page.locator('[data-testid="login-register-link"]');
    this.errorMessage = page.locator('[data-testid="login-error-alert"]');
    this.loadingSpinner = page.locator('.ant-spin');
    this.registrationOrganizationInput = page.locator(
      '[data-testid="registration-organization-input"]'
    );
    this.registrationEmailInput = page.locator('[data-testid="registration-email-input"]');
    this.registrationPasswordInput = page.locator('[data-testid="registration-password-input"]');
    this.registrationPasswordConfirmInput = page.locator(
      '[data-testid="registration-password-confirm-input"]'
    );
    this.registrationTermsCheckbox = page.locator('#termsAccepted');
    this.registrationSubmitButton = page.locator('[data-testid="registration-submit-button"]');
    this.registrationActivationCodeInput = page.locator(
      '[data-testid="registration-activation-code-input"]'
    );
    this.registrationVerifyButton = page.locator('[data-testid="registration-verify-button"]');
  }

  getPageLocators(): Record<string, Locator> {
    return {
      emailInput: this.emailInput,
      passwordInput: this.passwordInput,
      loginButton: this.loginButton,
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
      registrationVerifyButton: this.registrationVerifyButton,
    };
  }

  async login(email: string, password: string): Promise<void> {
    console.warn(`Logging in with email: ${email}`);
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.loginButton.click();
  }

  async loginWithValidation(email: string, password: string): Promise<void> {
    await this.verifyElementVisible(this.emailInput);
    await this.verifyElementVisible(this.passwordInput);
    await this.verifyElementVisible(this.loginButton);

    await this.login(email, password);
  }

  async waitForLoginCompletion(): Promise<void> {
    await this.waitForElementToDisappear(this.loadingSpinner, 10000);

    // Wait for critical API calls that indicate auth is complete
    // This is more reliable than networkidle which has browser-specific timing issues
    try {
      await this.page.waitForResponse(
        (response) => {
          const url = response.url();
          return (
            response.status() === 200 &&
            url.includes('/api/') &&
            (url.includes('Organization') || url.includes('Dashboard') || url.includes('Info'))
          );
        },
        { timeout: 10000 }
      );
    } catch {
      // Fallback: if no matching API response, continue anyway
      console.warn('No matching API response found, continuing with element visibility check');
    }

    // Then verify dashboard element is visible (mobile may hide header actions)
    const primary = this.page.locator('[data-testid="user-menu-button"]');
    const fallbackToggle = this.page.locator('[data-testid="sidebar-toggle-button"]');
    const fallbackContent = this.page.locator('[data-testid="main-content"]');

    await this.waitForAnyVisible([primary, fallbackToggle, fallbackContent], 15000);
  }

  private async waitForAnyVisible(locators: Locator[], timeout: number): Promise<void> {
    // Wait for any post-login element to become visible.
    const waits = locators.map((locator) => locator.waitFor({ state: 'visible', timeout }));
    try {
      await Promise.any(waits);
    } catch {
      throw new Error('Login completion timeout: no post-login element became visible.');
    }
  }

  async getErrorMessage(): Promise<string> {
    await this.waitForElement(this.errorMessage);
    return (await this.errorMessage.textContent()) ?? '';
  }

  async validateErrorMessage(expectedMessage?: string): Promise<boolean> {
    try {
      await this.waitForElement(this.errorMessage, 5000);
      const actualMessage = (await this.errorMessage.textContent()) ?? '';

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
    const state = loadGlobalState();
    console.warn(`Logging in with registered user: ${state.email}`);
    await this.login(state.email, state.password);
    await this.waitForLoginCompletion();
    console.warn('Authentication successful');
  }

  async fillRegistrationForm(
    organizationName: string,
    email: string,
    password: string,
    passwordConfirm: string,
    acceptTerms = true
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
  }

  async completeRegistration(
    organizationName: string,
    email: string,
    password: string,
    passwordConfirm: string,
    acceptTerms = true
  ): Promise<void> {
    await this.fillRegistrationForm(
      organizationName,
      email,
      password,
      passwordConfirm,
      acceptTerms
    );
    await this.submitRegistrationForm();
  }

  async completeRegistrationVerification(code?: string): Promise<void> {
    const activationCode = code ?? getEnvVarWithDefault('TEST_VERIFICATION_CODE');
    await this.registrationActivationCodeInput.fill(activationCode);
    await this.registrationVerifyButton.click();
    await this.waitForNetworkIdle();
  }
}
