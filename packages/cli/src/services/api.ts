import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import {
  normalizeResponse,
  createApiServices,
  parseFirst,
  responseExtractors,
} from '@rediacc/shared/api';
import type { ApiClient as SharedApiClient } from '@rediacc/shared/api';
import { createVaultEncryptor } from '@rediacc/shared/encryption';
import type { ApiResponse } from '@rediacc/shared/types';
import { nodeCryptoProvider } from '../adapters/crypto.js';
import { nodeStorageAdapter } from '../adapters/storage.js';
import { EXIT_CODES } from '../types/index.js';
import type { AuthResponse } from '../types/api-responses.js';

const API_PREFIX = '/StoredProcedure';
const STORAGE_KEYS = {
  TOKEN: 'token',
  API_URL: 'apiUrl',
  MASTER_PASSWORD: 'masterPassword',
} as const;

const vaultEncryptor = createVaultEncryptor(nodeCryptoProvider);

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

    // Load API URL from storage or use default
    const storedUrl = await nodeStorageAdapter.getItem(STORAGE_KEYS.API_URL);
    this.apiUrl = storedUrl || process.env.REDIACC_API_URL || 'https://www.rediacc.com/api';
    this.client.defaults.baseURL = `${this.apiUrl}${API_PREFIX}`;
    this.initialized = true;
  }

  async setApiUrl(url: string): Promise<void> {
    this.apiUrl = url;
    this.client.defaults.baseURL = `${url}${API_PREFIX}`;
    await nodeStorageAdapter.setItem(STORAGE_KEYS.API_URL, url);
  }

  getApiUrl(): string {
    return this.apiUrl;
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
      // Encrypt vault fields in request data if present
      let requestData = data || {};
      const masterPassword = await this.getMasterPassword();

      if (masterPassword && vaultEncryptor.hasVaultFields(requestData)) {
        requestData = await vaultEncryptor.encrypt(requestData, masterPassword);
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

      // Decrypt vault fields in response data
      if (masterPassword && vaultEncryptor.hasVaultFields(responseData)) {
        responseData = await vaultEncryptor.decrypt(responseData, masterPassword);
      }

      return normalizeResponse(responseData);
    } catch (error) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 401) {
          throw new CliApiError('Authentication required', EXIT_CODES.AUTH_REQUIRED);
        }
        if (error.response?.status === 403) {
          throw new CliApiError('Permission denied', EXIT_CODES.PERMISSION_DENIED);
        }
        if (error.response?.status === 404) {
          throw new CliApiError('Resource not found', EXIT_CODES.NOT_FOUND);
        }
        if (!error.response) {
          throw new CliApiError('Network error: ' + error.message, EXIT_CODES.NETWORK_ERROR);
        }
      }
      throw error;
    }
  }

  private async handleTokenRotation(response: ApiResponse): Promise<void> {
    const row = parseFirst<AuthResponse>(response as ApiResponse<AuthResponse>, {
      extractor: responseExtractors.primaryOrSecondary,
    });
    const newToken = row?.nextRequestToken;
    if (newToken) {
      await nodeStorageAdapter.setItem(STORAGE_KEYS.TOKEN, newToken);
    }
  }

  private async getToken(): Promise<string | null> {
    // Check environment variable first
    const envToken = process.env.REDIACC_TOKEN;
    if (envToken) return envToken;

    return nodeStorageAdapter.getItem(STORAGE_KEYS.TOKEN);
  }

  async setToken(token: string): Promise<void> {
    await nodeStorageAdapter.setItem(STORAGE_KEYS.TOKEN, token);
  }

  async clearToken(): Promise<void> {
    await nodeStorageAdapter.removeItem(STORAGE_KEYS.TOKEN);
  }

  async hasToken(): Promise<boolean> {
    const token = await this.getToken();
    return token !== null;
  }

  private createApiError(response: ApiResponse): CliApiError {
    const message = response.errors?.join('; ') || response.message || 'API request failed';
    return new CliApiError(message, EXIT_CODES.GENERAL_ERROR, response);
  }
}

export class CliApiError extends Error {
  constructor(
    message: string,
    public readonly exitCode: number = EXIT_CODES.GENERAL_ERROR,
    public readonly response?: ApiResponse
  ) {
    super(message);
    this.name = 'CliApiError';
  }
}

export const apiClient = new CliApiClient();
export const api = createApiServices(apiClient);
