import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import { createApiServices, normalizeResponse, extractNextToken, extractApiErrors, getPrimaryErrorMessage, HTTP_STATUS, isServerError } from '@rediacc/shared/api';
import type { ApiClient as SharedApiClient } from '@rediacc/shared/api';
import { createVaultEncryptor, isEncrypted } from '@rediacc/shared/encryption';
import type { ApiResponse } from '@rediacc/shared/types';
import { contextService } from './context.js';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import { EXIT_CODES } from '../types/index.js';
import type { ErrorCode } from '../types/errors.js';

const API_PREFIX = '/StoredProcedure';

const vaultEncryptor = createVaultEncryptor(nodeCryptoProvider);

/**
 * Check if an object contains any vault fields with actually encrypted content.
 * This differs from hasVaultFields() which only checks field names.
 * We check the actual content to determine if decryption is needed.
 */
function hasEncryptedVaultContent(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;

  const check = (obj: unknown): boolean => {
    if (!obj || typeof obj !== 'object') return false;

    if (Array.isArray(obj)) {
      return obj.some((item) => check(item));
    }

    for (const [key, val] of Object.entries(obj as Record<string, unknown>)) {
      // Check if this is a vault field with encrypted content
      if (key.toLowerCase().includes('vault') && typeof val === 'string') {
        if (isEncrypted(val)) {
          return true;
        }
      }
      // Recursively check nested objects
      if (val && typeof val === 'object' && check(val)) {
        return true;
      }
    }
    return false;
  };

  return check(value);
}

class CliApiClient implements SharedApiClient {
  private client: AxiosInstance;
  private apiUrl: string = '';
  private initialized = false;
  private masterPasswordGetter: (() => Promise<string>) | null = null;

  constructor() {
    this.client = axios.create({
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  setMasterPasswordGetter(getter: () => Promise<string>): void {
    this.masterPasswordGetter = getter;
  }

  private async getMasterPassword(): Promise<string | null> {
    if (this.masterPasswordGetter) {
      try {
        return await this.masterPasswordGetter();
      } catch {
        return null;
      }
    }
    return null;
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;

    // Load API URL from context service
    this.apiUrl = await contextService.getApiUrl();
    this.client.defaults.baseURL = `${this.apiUrl}${API_PREFIX}`;
    this.initialized = true;
  }

  /**
   * Reinitialize the API client (useful after context switch).
   */
  async reinitialize(): Promise<void> {
    this.initialized = false;
    await this.initialize();
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

  getApiUrl(): string {
    return this.apiUrl;
  }

  /**
   * Set the API URL directly (for register/activate commands that don't require a context).
   */
  async setApiUrl(url: string): Promise<void> {
    await this.initialize();
    this.apiUrl = this.normalizeApiUrl(url);
    this.client.defaults.baseURL = `${this.apiUrl}${API_PREFIX}`;
  }

  async login(
    email: string,
    passwordHash: string,
    sessionName = 'CLI Session'
  ): Promise<ApiResponse> {
    await this.initialize();

    const response = await this.client.post<ApiResponse>(
      '/CreateAuthenticationRequest',
      { name: sessionName },
      {
        headers: {
          'Rediacc-UserEmail': email,
          'Rediacc-UserHash': passwordHash,
        },
      }
    );

    const data = response.data;
    await this.handleTokenRotation(data);
    return data;
  }

  async logout(): Promise<ApiResponse> {
    return this.post('/DeleteUserRequest', {});
  }

  async activateUser(
    email: string,
    activationCode: string,
    passwordHash: string
  ): Promise<ApiResponse> {
    await this.initialize();

    const response = await this.client.post<ApiResponse>(
      '/ActivateUserAccount',
      { activationCode },
      {
        headers: {
          'Rediacc-UserEmail': email,
          'Rediacc-UserHash': passwordHash,
        },
      }
    );

    return response.data;
  }

  async register(
    companyName: string,
    email: string,
    passwordHash: string,
    languagePreference = 'en'
  ): Promise<ApiResponse> {
    await this.initialize();

    const response = await this.client.post<ApiResponse>(
      '/CreateNewCompany',
      {
        companyName,
        userEmailAddress: email,
        languagePreference,
      },
      {
        headers: {
          'Rediacc-UserEmail': email,
          'Rediacc-UserHash': passwordHash,
        },
      }
    );

    return response.data;
  }

  async get<T = unknown>(
    endpoint: string,
    params?: Record<string, unknown>,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    return this.makeRequest<T>(endpoint, params, config);
  }

  async post<T = unknown>(
    endpoint: string,
    data?: Record<string, unknown>,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    return this.makeRequest<T>(endpoint, data, config);
  }

  async put<T = unknown>(
    endpoint: string,
    data?: Record<string, unknown>,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    return this.makeRequest<T>(endpoint, data, config);
  }

  async delete<T = unknown>(
    endpoint: string,
    data?: Record<string, unknown>,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    return this.makeRequest<T>(endpoint, data, config);
  }

  private async makeRequest<T>(
    endpoint: string,
    data?: Record<string, unknown>,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    await this.initialize();

    const token = await this.getToken();
    const headers: Record<string, string> = {};

    // Copy string headers from config
    if (config?.headers) {
      for (const [key, value] of Object.entries(config.headers)) {
        if (typeof value === 'string') {
          headers[key] = value;
        }
      }
    }

    if (token) {
      headers['Rediacc-RequestToken'] = token;
    }

    try {
      // Encrypt vault fields in request data if present (only get password if needed)
      let requestData = data ?? {};
      let masterPassword: string | null = null;

      if (vaultEncryptor.hasVaultFields(requestData)) {
        masterPassword = await this.getMasterPassword();
        if (masterPassword) {
          requestData = await vaultEncryptor.encrypt(requestData, masterPassword);
        }
      }

      const response = await this.client.post<ApiResponse<T>>(endpoint, requestData, {
        ...config,
        headers,
      });

      let responseData = response.data;
      await this.handleTokenRotation(responseData);

      if (responseData.failure !== 0) {
        throw this.createApiError(responseData);
      }

      // Decrypt vault fields in response data (only if content is actually encrypted)
      // We check if vault fields contain encrypted content (not just if vault fields exist)
      // This prevents unnecessary master password prompts when company doesn't have encryption
      const hasEncrypted = hasEncryptedVaultContent(responseData);
      if (hasEncrypted) {
        masterPassword ??= await this.getMasterPassword();
        if (masterPassword) {
          responseData = await vaultEncryptor.decrypt(responseData, masterPassword);
        }
      }

      return normalizeResponse(responseData);
    } catch (error) {
      if (axios.isAxiosError(error)) {
        // Check if we have an API response with error details
        const responseData = error.response?.data as ApiResponse | undefined;
        if (responseData && typeof responseData === 'object' && 'failure' in responseData) {
          // Process API error response to extract details
          throw this.createApiError(responseData);
        }

        // Check for middleware HTTP error format: { error: "message" }
        const httpErrorData = error.response?.data as { error?: string } | undefined;
        if (httpErrorData && typeof httpErrorData === 'object' && 'error' in httpErrorData) {
          const errorMessage = httpErrorData.error ?? 'Request failed';
          const statusCode = error.response?.status ?? 400;
          const { code, exitCode } = this.mapFailureToError(statusCode);
          throw new CliApiError(errorMessage, code, exitCode, [errorMessage]);
        }

        // Handle HTTP status codes without API response body
        if (error.response?.status === 401) {
          throw new CliApiError(
            'Authentication required',
            'AUTH_REQUIRED',
            EXIT_CODES.AUTH_REQUIRED
          );
        }
        if (error.response?.status === 403) {
          throw new CliApiError(
            'Permission denied',
            'PERMISSION_DENIED',
            EXIT_CODES.PERMISSION_DENIED
          );
        }
        if (error.response?.status === 404) {
          throw new CliApiError('Resource not found', 'NOT_FOUND', EXIT_CODES.NOT_FOUND);
        }
        if (!error.response) {
          throw new CliApiError(
            `Network error: ${error.message}`,
            'NETWORK_ERROR',
            EXIT_CODES.NETWORK_ERROR
          );
        }
      }
      throw error;
    }
  }

  private async handleTokenRotation(response: ApiResponse): Promise<void> {
    const newToken = extractNextToken(response);
    if (newToken) {
      await contextService.setToken(newToken);
    }
  }

  private async getToken(): Promise<string | null> {
    return contextService.getToken();
  }

  async setToken(token: string): Promise<void> {
    await contextService.setToken(token);
  }

  async clearToken(): Promise<void> {
    await contextService.clearCredentials();
  }

  async hasToken(): Promise<boolean> {
    return contextService.hasToken();
  }

  private createApiError(response: ApiResponse): CliApiError {
    // Use shared utilities for error extraction
    const details = extractApiErrors(response);
    const message = getPrimaryErrorMessage(response);

    // Determine error code and exit code from failure value
    const { code, exitCode } = this.mapFailureToError(response.failure);

    return new CliApiError(message, code, exitCode, details, response);
  }

  private mapFailureToError(failure: number): { code: ErrorCode; exitCode: number } {
    // Map middleware return codes to error codes using shared HTTP_STATUS constants
    switch (failure) {
      case HTTP_STATUS.BAD_REQUEST:
        return { code: 'INVALID_REQUEST', exitCode: EXIT_CODES.INVALID_ARGUMENTS };
      case HTTP_STATUS.UNAUTHORIZED:
        return { code: 'AUTH_REQUIRED', exitCode: EXIT_CODES.AUTH_REQUIRED };
      case HTTP_STATUS.FORBIDDEN:
        return { code: 'PERMISSION_DENIED', exitCode: EXIT_CODES.PERMISSION_DENIED };
      case HTTP_STATUS.NOT_FOUND:
        return { code: 'NOT_FOUND', exitCode: EXIT_CODES.NOT_FOUND };
      case HTTP_STATUS.CONFLICT:
        return { code: 'INVALID_REQUEST', exitCode: EXIT_CODES.INVALID_ARGUMENTS };
      default:
        if (isServerError(failure)) {
          return { code: 'SERVER_ERROR', exitCode: EXIT_CODES.API_ERROR };
        }
        return { code: 'GENERAL_ERROR', exitCode: EXIT_CODES.GENERAL_ERROR };
    }
  }
}

export class CliApiError extends Error {
  constructor(
    message: string,
    public readonly code: ErrorCode = 'GENERAL_ERROR',
    public readonly exitCode: number = EXIT_CODES.GENERAL_ERROR,
    public readonly details: string[] = [],
    public readonly response?: ApiResponse
  ) {
    super(message);
    this.name = 'CliApiError';
  }
}

export const apiClient = new CliApiClient();
export const api = createApiServices(apiClient);
