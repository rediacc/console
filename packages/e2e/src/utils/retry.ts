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
 * Log retry attempt result.
 */
function logAttemptResult(
  attempt: number,
  maxRetries: number,
  duration: number,
  error?: unknown
): void {
  if (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.warn(`[Retry] Attempt ${attempt}/${maxRetries} failed after ${duration}ms: ${message}`);
  } else {
    console.warn(`[Retry] Network idle achieved on attempt ${attempt} in ${duration}ms`);
  }
}

/**
 * Handle fallback selector on final attempt.
 */
async function handleFallback(
  page: Page,
  fallbackSelector: string | undefined,
  timeout: number,
  maxRetries: number
): Promise<void> {
  if (!fallbackSelector) {
    console.warn(`[Retry] No fallback selector, throwing error`);
    throw new Error(`Network idle failed after ${maxRetries} attempts`);
  }

  console.warn(
    `[Retry] networkidle failed after ${maxRetries} attempts, falling back to selector: ${fallbackSelector}`
  );
  await page.locator(fallbackSelector).waitFor({ state: 'visible', timeout });
  console.warn(`[Retry] Fallback selector found, continuing`);
}

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
      logAttemptResult(attempt, maxRetries, Date.now() - attemptStart);
      return;
    } catch (error) {
      logAttemptResult(attempt, maxRetries, Date.now() - attemptStart, error);

      if (attempt === maxRetries) {
        await handleFallback(page, fallbackSelector, timeout, maxRetries);
        return;
      }

      console.warn(`[Retry] Retrying in ${retryDelay}ms...`);
      await new Promise((resolve) => setTimeout(resolve, retryDelay));
    }
  }
}
