import type { HttpRetryConfig } from './retry';
import type { VaultEncryptor } from '../../encryption';
import type { ApiResponse } from '../../types/api';
import type {
  TokenAdapter,
  ApiUrlProvider,
  MasterPasswordProvider,
  ErrorHandler,
  TelemetryHandler,
} from '../adapters/types';
import type { ApiClient } from '../services/types';

/**
 * HTTP client interface compatible with axios.
 */
export interface HttpClient {
  post<T = unknown>(
    url: string,
    data?: unknown,
    config?: { headers?: Record<string, string>; timeout?: number }
  ): Promise<{ data: T; status: number }>;
  defaults: {
    baseURL?: string;
    timeout?: number;
    headers?: Record<string, string>;
  };
}

/**
 * Configuration for creating an API client.
 */
export interface ApiClientConfig {
  /** HTTP client instance (axios or compatible) */
  httpClient: HttpClient;
  /** Adapter for token storage and retrieval */
  tokenAdapter: TokenAdapter;
  /** Provider for API URL resolution */
  urlProvider: ApiUrlProvider;
  /** Optional encryptor for vault fields */
  vaultEncryptor?: VaultEncryptor;
  /** Optional provider for master password */
  masterPasswordProvider?: MasterPasswordProvider;
  /** Optional handler for errors */
  errorHandler?: ErrorHandler;
  /** Optional handler for telemetry */
  telemetry?: TelemetryHandler;
  /** Optional retry configuration for transient errors (502, 503, 504, network errors) */
  retryConfig?: Partial<HttpRetryConfig>;
}

/**
 * Authentication client interface.
 */
export interface AuthClient {
  /** Login with email and password hash */
  login(email: string, passwordHash: string, sessionName?: string): Promise<ApiResponse>;
  /** Logout current session */
  logout(): Promise<ApiResponse>;
  /** Activate a user account */
  activateUser(email: string, activationCode: string, passwordHash: string): Promise<ApiResponse>;
  /** Register a new organization */
  register(
    organizationName: string,
    email: string,
    passwordHash: string,
    options?: { languagePreference?: string; turnstileToken?: string; subscriptionPlan?: string }
  ): Promise<ApiResponse>;
}

/**
 * Full API client interface combining CRUD and auth operations.
 */
export interface FullApiClient extends ApiClient, AuthClient {
  /** Update the API URL (useful after endpoint selection) */
  updateApiUrl(url: string): void;
  /** Reinitialize the client (useful after context switch) */
  reinitialize(): Promise<void>;
}
