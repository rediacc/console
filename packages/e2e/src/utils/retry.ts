import type { Page } from '@playwright/test';

export interface RetryOptions {
  maxRetries: number;
  retryDelay: number;
  timeout: number;
}

const DEFAULT_OPTIONS: RetryOptions = {
  maxRetries: 3,
  retryDelay: 1000,
  timeout: 15000,
};

/**
 * Wait for network idle with retry mechanism.
 * Falls back to a visible element check if networkidle keeps timing out.
 */
export async function waitForNetworkIdleWithRetry(
  page: Page,
  fallbackSelector?: string,
  options: Partial<RetryOptions> = {}
): Promise<void> {
  const { maxRetries, retryDelay, timeout } = { ...DEFAULT_OPTIONS, ...options };

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      await page.waitForLoadState('networkidle', { timeout });
      return;
    } catch (error) {
      const isLastAttempt = attempt === maxRetries;

      if (isLastAttempt) {
        // On last attempt, try fallback selector if provided
        if (fallbackSelector) {
          console.warn(
            `[Retry] networkidle failed after ${maxRetries} attempts, falling back to selector: ${fallbackSelector}`
          );
          await page.locator(fallbackSelector).waitFor({ state: 'visible', timeout });
          return;
        }
        throw error;
      }

      console.warn(
        `[Retry] networkidle attempt ${attempt}/${maxRetries} failed, retrying in ${retryDelay}ms...`
      );
      await new Promise((resolve) => setTimeout(resolve, retryDelay));
    }
  }
}
