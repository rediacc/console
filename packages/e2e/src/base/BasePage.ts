import { Page, Locator, expect } from '@playwright/test';
import { TIMEOUT_DEFAULTS } from '../utils/constants';

export abstract class BasePage {
  protected page: Page;
  protected url: string;

  constructor(page: Page, url: string) {
    this.page = page;
    this.url = url;
  }

  /**
   * Detect if running in Electron context.
   * Electron loads from file:// protocol, web loads from http(s)://
   * Note: We only check for file:// to avoid false positives from about:blank
   * which is the initial state for all browsers.
   */
  protected isElectronContext(): boolean {
    const currentUrl = this.page.url();
    return currentUrl.startsWith('file://');
  }

  /**
   * Normalize route by stripping /console prefix and ensuring leading slash.
   * /console/login -> /login
   * machines -> /machines
   */
  private normalizeRoute(route: string): string {
    let normalized = route;
    if (normalized.startsWith('/console')) {
      normalized = normalized.slice('/console'.length);
    }
    if (!normalized.startsWith('/')) {
      normalized = `/${normalized}`;
    }
    return normalized;
  }

  /**
   * Wait for a route to become active. Works for both Electron (HashRouter)
   * and Web (BrowserRouter) contexts.
   *
   * @param route - The route to wait for (e.g., '/machines', '/login')
   * @param options - Optional timeout configuration
   */
  protected async waitForRoute(route: string, options?: { timeout?: number }): Promise<void> {
    const timeout = options?.timeout ?? TIMEOUT_DEFAULTS.ROUTE;
    const normalizedRoute = this.normalizeRoute(route);

    if (this.isElectronContext()) {
      await this.page.waitForFunction(
        (expectedRoute) => {
          const hash = window.location.hash;
          const currentRoute = hash ? hash.slice(1) : '/';
          return currentRoute.includes(expectedRoute) || currentRoute === expectedRoute;
        },
        normalizedRoute,
        { timeout }
      );
    } else {
      await this.page.waitForURL(`**${normalizedRoute}*`, { timeout });
    }
  }

  async navigate(): Promise<void> {
    const normalizedRoute = this.normalizeRoute(this.url);

    if (this.isElectronContext()) {
      await this.page.evaluate((route) => {
        window.location.hash = route;
      }, normalizedRoute);
      await this.page.waitForTimeout(100);
    } else {
      await this.page.goto(this.url);
    }
    await this.waitForPageLoad();
  }

  async waitForPageLoad(): Promise<void> {
    await this.page.waitForLoadState('networkidle');
  }

  async getTitle(): Promise<string> {
    return await this.page.title();
  }

  getCurrentUrl(): string {
    return this.page.url();
  }

  async takeScreenshot(name: string): Promise<string> {
    const screenshotPath = `screenshots/${Date.now()}-${name}.png`;
    await this.page.screenshot({
      path: screenshotPath,
      fullPage: true,
    });
    return screenshotPath;
  }

  async scrollToElement(locator: Locator): Promise<void> {
    await locator.scrollIntoViewIfNeeded();
  }

  async waitForElement(locator: Locator, timeout = 10000): Promise<void> {
    await locator.waitFor({ state: 'visible', timeout });
  }

  async waitForElementToDisappear(locator: Locator, timeout = 10000): Promise<void> {
    await expect(locator).toBeHidden({ timeout });
  }

  async clickWithRetry(locator: Locator, _maxRetries = 1): Promise<void> {
    await locator.click();
  }

  async fillWithClear(locator: Locator, value: string): Promise<void> {
    await locator.clear();
    await locator.fill(value);
  }

  async selectOption(locator: Locator, value: string): Promise<void> {
    await locator.selectOption(value);
  }

  async uploadFile(locator: Locator, filePath: string): Promise<void> {
    await locator.setInputFiles(filePath);
  }

  async waitForAPIResponse(url: string | RegExp, timeout = 30000): Promise<void> {
    await this.page.waitForResponse(
      (response) =>
        typeof url === 'string' ? response.url().includes(url) : url.test(response.url()),
      { timeout }
    );
  }

  async verifyElementText(locator: Locator, expectedText: string): Promise<void> {
    await expect(locator).toHaveText(expectedText);
  }

  async verifyElementVisible(locator: Locator): Promise<void> {
    await expect(locator).toBeVisible();
  }

  async verifyElementHidden(locator: Locator): Promise<void> {
    await expect(locator).toBeHidden();
  }

  async verifyElementEnabled(locator: Locator): Promise<void> {
    await expect(locator).toBeEnabled();
  }

  async verifyElementDisabled(locator: Locator): Promise<void> {
    await expect(locator).toBeDisabled();
  }

  async getElementCount(locator: Locator): Promise<number> {
    return await locator.count();
  }

  async getAllTextContents(locator: Locator): Promise<string[]> {
    return await locator.allTextContents();
  }

  async closeDialog(): Promise<void> {
    const escapeKey = 'Escape';
    await this.page.keyboard.press(escapeKey);
  }

  async refreshPage(): Promise<void> {
    await this.page.reload();
    await this.waitForPageLoad();
  }

  async goBack(): Promise<void> {
    await this.page.goBack();
    await this.waitForPageLoad();
  }

  async goForward(): Promise<void> {
    await this.page.goForward();
    await this.waitForPageLoad();
  }

  async getDOMAttribute(locator: Locator, attributeName: string): Promise<string | null> {
    return await locator.getAttribute(attributeName);
  }

  async getCSSProperty(locator: Locator, propertyName: string): Promise<string> {
    return await locator.evaluate(
      (element, prop) => getComputedStyle(element).getPropertyValue(prop),
      propertyName
    );
  }

  async waitForNetworkIdle(): Promise<void> {
    await this.page.waitForLoadState('networkidle');
  }

  async mockAPIResponse(url: string | RegExp, responseData: unknown): Promise<void> {
    await this.page.route(url, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(responseData),
      });
    });
  }

  abstract getPageLocators(): Record<string, Locator>;
}
