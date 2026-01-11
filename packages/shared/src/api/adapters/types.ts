import type { TelemetryConfig, UserContext } from '../../telemetry/types';
import type { ApiResponse } from '../../types/api';
import type { ApiValidationError } from '../../types/api-schema.zod';

/**
 * Adapter for token storage and retrieval.
 * Implementations handle platform-specific storage (memory, file, etc.)
 */
export interface TokenAdapter {
  /** Get the current token, or null if not set */
  get(): Promise<string | null>;
  /** Store a new token */
  set(token: string): Promise<void>;
  /** Clear the stored token */
  clear(): Promise<void>;
}

/**
 * Provider for API URL resolution.
 * Implementations can perform health checks, use stored config, etc.
 */
export interface ApiUrlProvider {
  /** Get the API base URL (e.g., "http://localhost:7322/api") */
  getApiUrl(): Promise<string>;
}

/**
 * Provider for master password used in vault encryption.
 * Implementations can prompt users, read from config, etc.
 */
export interface MasterPasswordProvider {
  /** Get the master password, or null if not available */
  getMasterPassword(): Promise<string | null>;
}

/**
 * Handler for API errors.
 * Implementations can show UI messages, dispatch Redux actions, throw errors, etc.
 */
export interface ErrorHandler {
  /** Called when a 401 Unauthorized response is received */
  onUnauthorized(): void;
  /** Called when a 5xx server error occurs */
  onServerError?(message: string): void;
  /** Called when a network error occurs (no response) */
  onNetworkError?(message: string): void;
  /** Called when the API returns a non-zero failure code */
  onApiError?(failure: number, message: string, response: ApiResponse): void;
  /** Called when API response validation fails (schema mismatch) */
  onValidationError?(error: ApiValidationError): void;
}

/**
 * Handler for API telemetry/observability.
 * Implementations can log, send to analytics, etc.
 *
 * Required: trackApiCall (for API client integration)
 * Optional: Extended tracking methods for comprehensive telemetry
 */
export interface TelemetryHandler {
  /** Track an API call with its result (required) */
  trackApiCall(
    method: string,
    url: string,
    status: number | undefined,
    duration: number,
    error?: string
  ): void;

  /** Track a generic event with attributes (optional) */
  trackEvent?(eventName: string, attributes?: Record<string, unknown>): void;

  /** Track an error with context (optional) */
  trackError?(error: unknown, context?: Record<string, unknown>): void;

  /** Track a performance metric (optional) */
  trackMetric?(name: string, value: number, unit?: string): void;

  /** Set user context for attribution (optional) */
  setUserContext?(context: Partial<UserContext>): void;

  /** Initialize telemetry with configuration (optional) */
  initialize?(config: TelemetryConfig): void | Promise<void>;

  /** Shutdown telemetry and flush pending data (optional) */
  shutdown?(): void | Promise<void>;
}
