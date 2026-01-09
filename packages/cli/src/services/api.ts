import axios from 'axios';
import {
  createApiClient,
  createTypedApi,
  ApiClientError,
  type FullApiClient,
  type HttpClient,
  type MasterPasswordProvider,
  type ProcedureEndpoint,
} from '@rediacc/shared/api';
import { createVaultEncryptor } from '@rediacc/shared/encryption';
import type { ApiResponse } from '@rediacc/shared/types';
import { contextService } from './context.js';
import {
  nodeCryptoProvider,
  tokenAdapter,
  urlAdapter,
  errorHandler,
  telemetryAdapter,
} from '../adapters/index.js';
import { EXIT_CODES } from '../types/index.js';
import type { ErrorCode } from '../types/errors.js';

// Create axios instance
const axiosInstance = axios.create({
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * CLI-specific API client extending the shared factory with CLI features.
 */
class CliApiClient {
  private client: FullApiClient | null = null;
  private masterPasswordGetter: (() => Promise<string>) | null = null;
  private initialized = false;

  /**
   * Set a callback for getting the master password.
   * This is used by commands that need to encrypt/decrypt vault data.
   */
  setMasterPasswordGetter(getter: () => Promise<string>): void {
    this.masterPasswordGetter = getter;
  }

  /**
   * Initialize the client on first use.
   */
  private ensureInitialized(): FullApiClient {
    if (this.client && this.initialized) {
      return this.client;
    }

    const masterPasswordProvider: MasterPasswordProvider = {
      getMasterPassword: async () => {
        if (this.masterPasswordGetter) {
          try {
            return await this.masterPasswordGetter();
          } catch {
            return null;
          }
        }
        return null;
      },
    };

    this.client = createApiClient({
      httpClient: axiosInstance as unknown as HttpClient,
      tokenAdapter,
      urlProvider: urlAdapter,
      vaultEncryptor: createVaultEncryptor(nodeCryptoProvider),
      masterPasswordProvider,
      errorHandler,
      telemetry: telemetryAdapter,
    });

    this.initialized = true;
    return this.client;
  }

  /**
   * Reinitialize the API client (useful after context switch).
   */
  async reinitialize(): Promise<void> {
    this.initialized = false;
    const client = this.ensureInitialized();
    await client.reinitialize();
  }

  /**
   * Normalize an API URL to ensure it ends with /api.
   */
  normalizeApiUrl(url: string): string {
    let normalizedUrl = url.replace(/\/+$/, '');
    if (!normalizedUrl.endsWith('/api')) {
      normalizedUrl = `${normalizedUrl}/api`;
    }
    return normalizedUrl;
  }

  /**
   * Get the current API URL.
   */
  async getApiUrl(): Promise<string> {
    return contextService.getApiUrl();
  }

  /**
   * Set the API URL directly (for register/activate commands that don't require a context).
   */
  setApiUrl(url: string): void {
    const client = this.ensureInitialized();
    client.updateApiUrl(this.normalizeApiUrl(url));
  }

  // Auth methods
  async login(
    email: string,
    passwordHash: string,
    sessionName = 'CLI Session'
  ): Promise<ApiResponse> {
    const client = this.ensureInitialized();
    return client.login(email, passwordHash, sessionName);
  }

  async logout(): Promise<ApiResponse> {
    const client = this.ensureInitialized();
    return client.logout();
  }

  async activateUser(
    email: string,
    activationCode: string,
    passwordHash: string
  ): Promise<ApiResponse> {
    const client = this.ensureInitialized();
    return client.activateUser(email, activationCode, passwordHash);
  }

  async register(
    organizationName: string,
    email: string,
    passwordHash: string,
    subscriptionPlan = 'COMMUNITY',
    languagePreference = 'en'
  ): Promise<ApiResponse> {
    const client = this.ensureInitialized();
    return client.register(organizationName, email, passwordHash, {
      languagePreference,
      subscriptionPlan,
    });
  }

  // CRUD methods (typed - only accepts known endpoints)
  async get<T = unknown>(
    endpoint: ProcedureEndpoint,
    params?: Record<string, unknown>,
    _config?: Record<string, unknown>
  ): Promise<ApiResponse<T>> {
    const client = this.ensureInitialized();
    return client.get<T>(endpoint, params);
  }

  async post<T = unknown>(
    endpoint: ProcedureEndpoint,
    data?: Record<string, unknown>,
    _config?: Record<string, unknown>
  ): Promise<ApiResponse<T>> {
    const client = this.ensureInitialized();
    return client.post<T>(endpoint, data);
  }

  async put<T = unknown>(
    endpoint: ProcedureEndpoint,
    data?: Record<string, unknown>,
    _config?: Record<string, unknown>
  ): Promise<ApiResponse<T>> {
    const client = this.ensureInitialized();
    return client.put<T>(endpoint, data);
  }

  async delete<T = unknown>(
    endpoint: ProcedureEndpoint,
    data?: Record<string, unknown>,
    _config?: Record<string, unknown>
  ): Promise<ApiResponse<T>> {
    const client = this.ensureInitialized();
    return client.delete<T>(endpoint, data);
  }

  // Token management utilities
  async setToken(token: string): Promise<void> {
    await tokenAdapter.set(token);
  }

  async clearToken(): Promise<void> {
    await tokenAdapter.clear();
  }

  async hasToken(): Promise<boolean> {
    return contextService.hasToken();
  }
}

/**
 * CLI-specific API error with exit code.
 * Extends the shared ApiClientError with CLI-specific exit codes.
 */
export class CliApiError extends ApiClientError {
  public override readonly name = 'CliApiError';
  public readonly exitCode: number;

  constructor(
    message: string,
    code: ErrorCode = 'GENERAL_ERROR',
    exitCode: number = EXIT_CODES.GENERAL_ERROR,
    details: string[] = [],
    response?: ApiResponse
  ) {
    super(message, code, details, response);
    this.exitCode = exitCode;
  }
}

// Export singleton instance
export const apiClient = new CliApiClient();
export const typedApi = createTypedApi(apiClient);
