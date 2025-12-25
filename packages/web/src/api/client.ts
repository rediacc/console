import axios, {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
  InternalAxiosRequestConfig,
  isAxiosError,
} from 'axios';
import { apiConnectionService } from '@/services/api';
import { tokenService } from '@/services/auth';
import { telemetryService } from '@/services/telemetryService';
import { logout, showSessionExpiredModal } from '@/store/auth/authSlice';
import { store } from '@/store/store';
import { showMessage } from '@/utils/messages';
import { createApiServices, normalizeResponse } from '@rediacc/shared/api';
import type { ApiClient as SharedApiClient } from '@rediacc/shared/api';
import type { ApiResponse } from '@rediacc/shared/types';
import { decryptResponseData, encryptRequestData, hasVaultFields } from './encryptionMiddleware';

// Extend axios config to include metadata
declare module 'axios' {
  interface InternalAxiosRequestConfig {
    metadata?: {
      startTime: number;
    };
  }
}

// API configuration
const API_PREFIX = '/StoredProcedure';

// API URL will be determined dynamically based on connection health check
let API_BASE_URL = '';

class ApiClient implements SharedApiClient {
  private client: AxiosInstance;
  private requestQueue: Promise<void> = Promise.resolve();

  private readonly HTTP_UNAUTHORIZED = 401;
  private readonly HTTP_SERVER_ERROR = 500;

  // Method to update API URL dynamically
  updateApiUrl(newUrl: string) {
    API_BASE_URL = newUrl;
    this.client.defaults.baseURL = API_BASE_URL + API_PREFIX;
  }

  constructor() {
    // Initialize with empty baseURL, will be set after health check
    this.client = axios.create({
      baseURL: '',
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.setupInterceptors();
    void this.initializeBaseUrl();
  }

  private async initializeBaseUrl() {
    // Get the API URL from connection service (will perform health check if needed)
    const apiUrl = await apiConnectionService.getApiUrl();
    API_BASE_URL = apiUrl;
    this.client.defaults.baseURL = `${API_BASE_URL}${API_PREFIX}`;
  }

  private setupInterceptors() {
    this.client.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
      // Add request start time for telemetry
      config.metadata = { startTime: performance.now() };

      const token = await tokenService.getToken();
      if (token) {
        config.headers['Rediacc-RequestToken'] = token;
      } else {
        console.warn('No token available for request:', config.url);
      }

      if (config.data && hasVaultFields(config.data)) {
        config.data = await encryptRequestData(config.data);
      }
      return config;
    });

    this.client.interceptors.response.use(
      async (response) => {
        const startTime = response.config.metadata?.startTime ?? 0;
        const duration = performance.now() - startTime;

        let responseData = await this.handleResponseDecryption(response.data as ApiResponse);
        responseData = normalizeResponse(responseData);
        response.data = responseData;

        // Track successful API call
        telemetryService.trackApiCall(
          response.config.method?.toUpperCase() ?? 'UNKNOWN',
          response.config.url ?? '',
          response.status,
          duration
        );

        // CRITICAL: Save token BEFORE checking for errors
        // If the server sent a token, it means the token was rotated in the database
        // (even if subsequent operations failed), so we MUST save it to stay synchronized
        await this.handleTokenRotation(responseData);

        if (responseData.failure !== 0) return this.handleApiFailure(responseData);

        return response;
      },
      (error: AxiosError<ApiResponse>) => {
        const startTime = error.config?.metadata?.startTime ?? 0;
        const duration = performance.now() - startTime;

        // Track failed API call
        telemetryService.trackApiCall(
          error.config?.method?.toUpperCase() ?? 'UNKNOWN',
          error.config?.url ?? '',
          error.response?.status,
          duration,
          error.message
        );

        return this.handleResponseError(error);
      }
    );
  }

  async login(email: string, passwordHash: string, sessionName = 'Web Session') {
    // Ensure API URL is initialized before login
    if (!API_BASE_URL) {
      await this.initializeBaseUrl();
    }

    // Route through request queue for consistency and proper token handling
    return this.queueRequest(async () => {
      // Use the configured axios instance for consistent interceptor handling
      return this.client.post<ApiResponse>(
        '/CreateAuthenticationRequest',
        { name: sessionName },
        {
          headers: {
            'Rediacc-UserEmail': email,
            'Rediacc-UserHash': passwordHash,
          },
        }
      );
    });
  }

  async logout() {
    return (await this.client.post<ApiResponse>('/DeleteUserRequest', {})).data;
  }

  async activateUser(email: string, activationCode: string, passwordHash: string) {
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

  private async makeRequest<T>(
    endpoint: string,
    data?: unknown,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> {
    const payload = data ?? {};
    return this.queueRequest(() => this.client.post<ApiResponse<T>>(endpoint, payload, config));
  }

  get = <T>(
    endpoint: string,
    params?: unknown,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> => this.makeRequest<T>(endpoint, params, config);

  post = <T>(
    endpoint: string,
    data: unknown,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> => this.makeRequest<T>(endpoint, data, config);

  put = <T>(
    endpoint: string,
    data: unknown,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> => this.makeRequest<T>(endpoint, data, config);

  delete = <T>(
    endpoint: string,
    data: unknown,
    config?: AxiosRequestConfig
  ): Promise<ApiResponse<T>> => this.makeRequest<T>(endpoint, data, config);

  private async queueRequest<T>(
    request: () => Promise<AxiosResponse<ApiResponse<T>>>
  ): Promise<ApiResponse<T>> {
    const nextRequest = this.requestQueue
      .catch(() => undefined)
      .then(async () => (await request()).data);

    this.requestQueue = nextRequest.then(
      () => undefined,
      () => undefined
    );

    return nextRequest;
  }

  private async handleResponseDecryption(responseData: ApiResponse): Promise<ApiResponse> {
    if (!hasVaultFields(responseData)) return responseData;
    try {
      return await decryptResponseData(responseData);
    } catch {
      return responseData;
    }
  }

  private extractErrorMessage(error: unknown): string {
    if (typeof error === 'string') {
      return error;
    }

    if (this.isApiResponse(error)) {
      const errorText = error.errors.length > 0 ? error.errors.join('; ') : error.message;
      return errorText || 'Request failed';
    }

    if (isAxiosError<ApiResponse>(error)) {
      const data = error.response?.data;
      const responseErrors = data?.errors.join('; ');
      const responseMessage = data?.message;
      const nestedMessageEntry = data?.resultSets[0]?.data[0] as { message?: string } | undefined;
      const nestedMessage = nestedMessageEntry?.message;
      const additionalErrors = (error as { errors?: string[] }).errors?.join('; ');
      if (responseErrors) return responseErrors;
      if (responseMessage) return responseMessage;
      if (nestedMessage) return nestedMessage;
      if (additionalErrors) return additionalErrors;
      return error.message;
    }

    if (error instanceof Error) {
      return error.message;
    }

    return 'Request failed';
  }

  private isUnauthorizedError(error: ApiResponse | AxiosError<ApiResponse>): boolean {
    if (this.isApiResponse(error)) {
      return error.failure === this.HTTP_UNAUTHORIZED;
    }
    return error.response?.status === this.HTTP_UNAUTHORIZED;
  }

  private handleUnauthorizedError(): void {
    const currentPath = window.location.pathname;
    const isAlreadyOnLogin = currentPath.includes('/login');

    // Only show dialog if not already on login page and dialog not already shown
    if (!isAlreadyOnLogin) {
      const state = store.getState();
      if (!state.auth.showSessionExpiredModal) {
        showMessage('error', 'Session expired. Please login again.');
        store.dispatch(logout());
        store.dispatch(showSessionExpiredModal());
      }
    }
  }

  private handleApiFailure(responseData: ApiResponse): Promise<never> {
    if (this.isUnauthorizedError(responseData)) {
      this.handleUnauthorizedError();
      throw new Error('Unauthorized');
    }
    throw new Error(this.extractErrorMessage(responseData));
  }

  private async handleTokenRotation(responseData: ApiResponse): Promise<void> {
    // For ForkAuthenticationRequest, only rotate the main session token (resultSets[0])
    // Don't use the fork token from the "Credentials" resultSet for main session rotation
    const rotationSource = responseData.resultSets[0]?.data[0] as
      | { nextRequestToken?: string }
      | undefined;
    const newToken = rotationSource?.nextRequestToken;
    if (!newToken) return;

    // Token rotation is now handled by tokenService with proper locking
    // No need for manual flag management or arbitrary delays
    await tokenService.updateToken(newToken);
  }

  private handleResponseError(error: AxiosError<ApiResponse>): Promise<never> {
    const responseStatus = error.response?.status;
    const isNetworkError = Boolean(error.request && !error.response);
    const errorHandlers = {
      [this.isUnauthorizedError(error) ? 'unauthorized' : '']: () => this.handleUnauthorizedError(),
      [responseStatus !== undefined && responseStatus >= this.HTTP_SERVER_ERROR ? 'server' : '']:
        () => showMessage('error', 'Server error. Please try again later.'),
      [isNetworkError ? 'network' : '']: () =>
        showMessage('error', 'Network error. Please check your connection.'),
    };

    Object.entries(errorHandlers).forEach(([key, handler]) => key && handler());

    const customError: Error & { response?: unknown } = new Error(this.extractErrorMessage(error));
    customError.response = error.response;
    throw customError;
  }

  private isApiResponse(value: unknown): value is ApiResponse {
    return (
      typeof value === 'object' && value !== null && 'failure' in value && 'resultSets' in value
    );
  }
}

export const apiClient = new ApiClient();
export const api = createApiServices(apiClient);
export default apiClient;
