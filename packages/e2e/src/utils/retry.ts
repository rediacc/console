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

  console.warn(
    `[Retry] Starting networkidle wait (${maxRetries} attempts, ${timeout}ms timeout each)`
  );

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    const attemptStart = Date.now();
    console.warn(`[Retry] Attempt ${attempt}/${maxRetries} - waiting for networkidle...`);

    try {
      await page.waitForLoadState('networkidle', { timeout });
      const duration = Date.now() - attemptStart;
      console.warn(`[Retry] Network idle achieved on attempt ${attempt} in ${duration}ms`);
      return;
    } catch (error) {
      const duration = Date.now() - attemptStart;
      const isLastAttempt = attempt === maxRetries;

      console.warn(
        `[Retry] Attempt ${attempt}/${maxRetries} failed after ${duration}ms: ${error instanceof Error ? error.message : String(error)}`
      );

      if (isLastAttempt) {
        // On last attempt, try fallback selector if provided
        if (fallbackSelector) {
          console.warn(
            `[Retry] networkidle failed after ${maxRetries} attempts, falling back to selector: ${fallbackSelector}`
          );
          await page.locator(fallbackSelector).waitFor({ state: 'visible', timeout });
          console.warn(`[Retry] Fallback selector found, continuing`);
          return;
        }
        console.warn(`[Retry] No fallback selector, throwing error`);
        throw error;
      }

      console.warn(
        `[Retry] networkidle attempt ${attempt}/${maxRetries} failed, retrying in ${retryDelay}ms...`
      );
      await new Promise((resolve) => setTimeout(resolve, retryDelay));
    }
  }
}
