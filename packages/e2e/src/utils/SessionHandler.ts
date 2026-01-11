import { Page } from '@playwright/test';

/**
 * Handles the Session Expired modal that can appear during long-running tests.
 * The modal appears when the user's session has expired for security reasons.
 */
export class SessionHandler {
  constructor(private page: Page) {}

  /**
   * Check if session expired modal is visible and dismiss it.
   * Returns true if modal was dismissed, false if no modal was present.
   */
  async dismissSessionExpiredModal(): Promise<boolean> {
    try {
      const sessionExpiredModal = this.page.locator('[data-testid="session-expired-modal"]');
      const isVisible = await sessionExpiredModal.isVisible({ timeout: 1000 }).catch(() => false);

      if (isVisible) {
        console.log('⚠️ Session expired modal detected - dismissing...');

        // Click the "Stay Logged Out" button to dismiss the modal
        const stayLoggedOutButton = this.page.locator('[data-testid="session-expired-stay-button"]');
        if (await stayLoggedOutButton.isVisible({ timeout: 500 }).catch(() => false)) {
          await stayLoggedOutButton.click();
          console.log('✅ Session expired modal dismissed via Stay Logged Out button');
          return true;
        }

        // Fallback: Click "Continue to Login" button
        const continueToLoginButton = this.page.locator('[data-testid="session-expired-login-button"]');
        if (await continueToLoginButton.isVisible({ timeout: 500 }).catch(() => false)) {
          await continueToLoginButton.click();
          console.log('✅ Session expired modal dismissed via Continue to Login button');
          return true;
        }
      }
      return false;
    } catch {
      return false;
    }
  }

  /**
   * Setup a listener that automatically dismisses session expired modals.
   * Call this once at the start of a test that might run long.
   */
  setupAutoHandler(): void {
    // Set up a mutation observer to detect when modal appears
    this.page.addLocatorHandler(
      this.page.locator('[data-testid="session-expired-modal"]'),
      async () => {
        console.log('⚠️ Session expired modal appeared - auto-dismissing...');
        const stayLoggedOutButton = this.page.locator('[data-testid="session-expired-stay-button"]');
        if (await stayLoggedOutButton.isVisible({ timeout: 500 }).catch(() => false)) {
          await stayLoggedOutButton.click();
        }
      }
    );
  }
}
