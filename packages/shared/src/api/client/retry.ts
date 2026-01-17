/**
 * Retry configuration for transient HTTP errors.
 */
export interface HttpRetryConfig {
  /** Maximum number of retry attempts (default: 3) */
  maxRetries: number;
  /** Base delay in milliseconds (default: 1000) */
  baseDelayMs: number;
  /** Maximum delay in milliseconds (default: 10000) */
  maxDelayMs: number;
  /** HTTP status codes that should trigger a retry */
  retryableStatuses: number[];
  /** Whether to retry on network errors (default: true) */
  retryOnNetworkError: boolean;
}

/**
 * Default retry configuration.
 * - 3 retries with exponential backoff: 1s → 2s → 4s
 * - Retries on: 408 (timeout), 429 (rate limit), 502, 503, 504 (gateway errors)
 * - Retries on network errors (no response)
 */
export const DEFAULT_HTTP_RETRY_CONFIG: HttpRetryConfig = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 10000,
  retryableStatuses: [408, 429, 502, 503, 504],
  retryOnNetworkError: true,
};

/**
 * Check if an error is an axios-like HTTP error.
 */
function isHttpError(
  error: unknown
): error is Error & { response?: { status: number }; request?: unknown; code?: string } {
  return error instanceof Error && ('response' in error || 'request' in error || 'code' in error);
}

/**
 * Check if an error should trigger a retry based on the configuration.
 */
export function isRetryableError(error: unknown, config: HttpRetryConfig): boolean {
  if (!isHttpError(error)) {
    return false;
  }

  // Network error (no response received) - e.g., ECONNREFUSED, ETIMEDOUT
  if (config.retryOnNetworkError && error.request && !error.response) {
    return true;
  }

  // Axios network error codes
  if (config.retryOnNetworkError && error.code) {
    const retryableCodes = [
      'ECONNABORTED',
      'ECONNREFUSED',
      'ECONNRESET',
      'ETIMEDOUT',
      'ERR_NETWORK',
    ];
    if (retryableCodes.includes(error.code)) {
      return true;
    }
  }

  // Check if HTTP status is in retryable list
  if (error.response?.status) {
    return config.retryableStatuses.includes(error.response.status);
  }

  return false;
}

/**
 * Calculate delay for a retry attempt using exponential backoff with jitter.
 * Formula: min(baseDelayMs * 2^attempt, maxDelayMs) + jitter
 *
 * @param attempt - Zero-based attempt number (0 = first retry)
 * @param config - Retry configuration
 * @returns Delay in milliseconds
 */
export function calculateDelay(attempt: number, config: HttpRetryConfig): number {
  // Exponential backoff: 1s, 2s, 4s, 8s...
  const exponentialDelay = config.baseDelayMs * Math.pow(2, attempt);

  // Cap at maxDelayMs
  const cappedDelay = Math.min(exponentialDelay, config.maxDelayMs);

  // Add jitter (±10%) to prevent thundering herd
  const jitter = cappedDelay * 0.1 * (Math.random() * 2 - 1);

  return Math.floor(cappedDelay + jitter);
}

/**
 * Sleep for a specified duration.
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Check if retry should be attempted based on attempt number and error type.
 */
function shouldRetry(error: unknown, attempt: number, config: HttpRetryConfig): boolean {
  if (attempt >= config.maxRetries) {
    return false;
  }
  return isRetryableError(error, config);
}

/**
 * Log retry attempt in non-production environments.
 */
function logRetryAttempt(attempt: number, maxRetries: number, error: unknown, delay: number): void {
  if (process.env.NODE_ENV === 'production') {
    return;
  }
  const errorMessage = error instanceof Error ? error.message : 'Unknown error';
  console.warn(
    `[API Retry] Attempt ${attempt + 1}/${maxRetries} failed: ${errorMessage}. Retrying in ${delay}ms...`
  );
}

/**
 * Execute an async function with automatic retry on transient errors.
 *
 * @param fn - The async function to execute
 * @param config - Optional partial retry configuration (merged with defaults)
 * @returns The result of the function
 * @throws The last error if all retries fail
 *
 * @example
 * const result = await withRetry(
 *   () => httpClient.post('/endpoint', data),
 *   { maxRetries: 5 }
 * );
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  config?: Partial<HttpRetryConfig>
): Promise<T> {
  const fullConfig: HttpRetryConfig = { ...DEFAULT_HTTP_RETRY_CONFIG, ...config };
  let lastError: unknown;

  for (let attempt = 0; attempt <= fullConfig.maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (!shouldRetry(error, attempt, fullConfig)) {
        break;
      }

      const delay = calculateDelay(attempt, fullConfig);
      logRetryAttempt(attempt, fullConfig.maxRetries, error, delay);
      await sleep(delay);
    }
  }

  throw lastError;
}
