import { isApiResponse } from '../../types/api';
import { extractApiErrors, getPrimaryErrorMessage } from '../errorUtils';
import { normalizeResponse } from '../normalizer';
import { HTTP_STATUS, isServerError } from '../statusCodes';
import { extractNextToken } from '../tokenUtils';
import { ApiClientError, API_ERROR_CODES, type ApiErrorCode } from './error';
import { RequestQueue } from './requestQueue';
import { withRetry, DEFAULT_HTTP_RETRY_CONFIG, type HttpRetryConfig } from './retry';
import { DEFAULTS } from '../../config';
import type { ApiClientConfig, FullApiClient } from './types';
import type { ApiResponse } from '../../types/api';
import type { ProcedureEndpoint } from '../services/types';

const API_PREFIX = '/StoredProcedure';

/**
 * Check if error is an axios-like error with response property.
 */
function isHttpError(
  error: unknown
): error is Error & { response?: { status: number; data: unknown }; request?: unknown } {
  return error instanceof Error && ('response' in error || 'request' in error);
}

/**
 * Map HTTP status/failure code to error code.
 */
function mapStatusToErrorCode(status: number): ApiErrorCode {
  switch (status) {
    case HTTP_STATUS.UNAUTHORIZED:
      return API_ERROR_CODES.UNAUTHORIZED;
    case HTTP_STATUS.FORBIDDEN:
      return API_ERROR_CODES.FORBIDDEN;
    case HTTP_STATUS.NOT_FOUND:
      return API_ERROR_CODES.NOT_FOUND;
    case HTTP_STATUS.BAD_REQUEST:
      return API_ERROR_CODES.BAD_REQUEST;
    case HTTP_STATUS.CONFLICT:
      return API_ERROR_CODES.CONFLICT;
    default:
      if (isServerError(status)) {
        return API_ERROR_CODES.SERVER_ERROR;
      }
      return API_ERROR_CODES.GENERAL_ERROR;
  }
}

/**
 * Build auth headers for login/register requests.
 */
function buildAuthHeaders(email: string, passwordHash: string): Record<string, string> {
  return {
    'Rediacc-UserEmail': email,
    'Rediacc-UserHash': passwordHash,
  };
}

/**
 * Create a unified API client with dependency injection for platform-specific concerns.
 *
 * @example
 * // Web usage
 * const client = createApiClient({
 *   httpClient: axios.create({ timeout: 30000 }),
 *   tokenAdapter: tokenServiceAdapter,
 *   urlProvider: apiConnectionServiceAdapter,
 *   vaultEncryptor: createVaultEncryptor(webCryptoProvider),
 *   masterPasswordProvider: masterPasswordServiceAdapter,
 *   errorHandler: webErrorHandler,
 *   telemetry: telemetryServiceAdapter,
 * });
 *
 * @example
 * // CLI usage
 * const client = createApiClient({
 *   httpClient: axios.create({ timeout: 30000 }),
 *   tokenAdapter: contextServiceAdapter,
 *   urlProvider: contextServiceAdapter,
 *   vaultEncryptor: createVaultEncryptor(nodeCryptoProvider),
 *   masterPasswordProvider: { getMasterPassword: masterPasswordGetter },
 *   errorHandler: cliErrorHandler,
 * });
 */
export function createApiClient(config: ApiClientConfig): FullApiClient {
  const {
    httpClient,
    tokenAdapter,
    urlProvider,
    vaultEncryptor,
    masterPasswordProvider,
    errorHandler,
    telemetry,
    retryConfig: userRetryConfig,
  } = config;

  // Merge user retry config with defaults
  const retryConfig: HttpRetryConfig = { ...DEFAULT_HTTP_RETRY_CONFIG, ...userRetryConfig };

  const requestQueue = new RequestQueue();

  // Track initialization
  let initialized = false;
  let apiBaseUrl = '';

  /**
   * Initialize the client by fetching the API URL.
   */
  async function initialize(): Promise<void> {
    if (initialized) return;
    apiBaseUrl = await urlProvider.getApiUrl();
    httpClient.defaults.baseURL = `${apiBaseUrl}${API_PREFIX}`;
    initialized = true;
  }

  /**
   * Reinitialize the client (useful after context switch).
   */
  async function reinitialize(): Promise<void> {
    initialized = false;
    await initialize();
  }

  /**
   * Update the API URL directly.
   */
  function updateApiUrl(url: string): void {
    apiBaseUrl = url;
    httpClient.defaults.baseURL = `${apiBaseUrl}${API_PREFIX}`;
    initialized = true; // Prevent initialize() from overwriting
  }

  /**
   * Get master password if available.
   */
  async function getMasterPassword(): Promise<string | null> {
    if (!masterPasswordProvider) return null;
    try {
      return await masterPasswordProvider.getMasterPassword();
    } catch {
      return null;
    }
  }

  /**
   * Encrypt vault fields in request data if needed.
   */
  async function encryptRequestData<T>(data: T): Promise<T> {
    if (!vaultEncryptor || !data) return data;
    if (!vaultEncryptor.hasVaultFields(data)) return data;

    const password = await getMasterPassword();
    if (!password) return data;

    return vaultEncryptor.encrypt(data, password);
  }

  /**
   * Decrypt vault fields in response data if needed.
   */
  async function decryptResponseData<T>(response: ApiResponse<T>): Promise<ApiResponse<T>> {
    if (!vaultEncryptor) return response;
    if (!vaultEncryptor.hasVaultFields(response)) return response;

    const password = await getMasterPassword();
    if (!password) return response;

    try {
      return await vaultEncryptor.decrypt(response, password);
    } catch {
      // Return original data if decryption fails
      return response;
    }
  }

  /**
   * Handle token rotation from response.
   */
  async function handleTokenRotation(response: ApiResponse): Promise<void> {
    const newToken = extractNextToken(response);
    if (newToken) {
      await tokenAdapter.set(newToken);
    }
  }

  /**
   * Create an ApiClientError from a response.
   */
  function createApiError(response: ApiResponse): ApiClientError {
    const details = extractApiErrors(response);
    const message = getPrimaryErrorMessage(response);
    const code = mapStatusToErrorCode(response.failure);
    return new ApiClientError(message, code, details, response);
  }

  /**
   * Handle API failure (non-zero failure code in response).
   */
  function handleApiFailure(response: ApiResponse): never {
    const isUnauthorized = response.failure === HTTP_STATUS.UNAUTHORIZED;

    if (isUnauthorized && errorHandler?.onUnauthorized) {
      errorHandler.onUnauthorized();
    }

    if (errorHandler?.onApiError) {
      const message = getPrimaryErrorMessage(response);
      errorHandler.onApiError(response.failure, message, response);
    }

    throw createApiError(response);
  }

  /**
   * Handle HTTP errors from the request.
   */
  function handleHttpError(error: unknown): never {
    if (!isHttpError(error)) {
      throw error;
    }

    const responseData = error.response?.data;
    const responseStatus = error.response?.status;

    // Check if we have an API response with error details
    if (responseData && isApiResponse(responseData)) {
      throw createApiError(responseData);
    }

    // Handle HTTP status codes without API response body
    if (responseStatus === HTTP_STATUS.UNAUTHORIZED) {
      errorHandler?.onUnauthorized();
      throw new ApiClientError('Authentication required', API_ERROR_CODES.UNAUTHORIZED);
    }

    if (responseStatus === HTTP_STATUS.FORBIDDEN) {
      throw new ApiClientError('Permission denied', API_ERROR_CODES.FORBIDDEN);
    }

    if (responseStatus === HTTP_STATUS.NOT_FOUND) {
      throw new ApiClientError('Resource not found', API_ERROR_CODES.NOT_FOUND);
    }

    if (responseStatus && isServerError(responseStatus)) {
      const message = 'Server error. Please try again later.';
      errorHandler?.onServerError?.(message);
      throw new ApiClientError(message, API_ERROR_CODES.SERVER_ERROR);
    }

    // Network error (no response)
    if (error.request && !error.response) {
      const message = `Network error: ${error.message}`;
      errorHandler?.onNetworkError?.(message);
      throw new ApiClientError(message, API_ERROR_CODES.NETWORK_ERROR);
    }

    throw new ApiClientError(error.message, API_ERROR_CODES.GENERAL_ERROR);
  }

  /**
   * Make an API request with all middleware applied.
   */
  async function makeRequest<T>(
    endpoint: ProcedureEndpoint,
    data?: Record<string, unknown>,
    additionalHeaders?: Record<string, string>
  ): Promise<ApiResponse<T>> {
    await initialize();

    return requestQueue.enqueue(async () => {
      const startTime = performance.now();
      const url = endpoint;

      try {
        // Get token
        const token = await tokenAdapter.get();
        const headers: Record<string, string> = { ...additionalHeaders };
        if (token) {
          headers['Rediacc-RequestToken'] = token;
        }

        // Encrypt vault fields if needed
        const requestData = await encryptRequestData(data ?? {});

        // Make request with automatic retry on transient errors
        const response = await withRetry(
          () => httpClient.post<ApiResponse<T>>(url, requestData, { headers }),
          retryConfig
        );

        // Track telemetry
        const duration = performance.now() - startTime;
        telemetry?.trackApiCall('POST', url, response.status, duration);

        // Process response
        let responseData = response.data;

        // CRITICAL: Save token BEFORE checking for errors
        // If the server sent a token, it means the token was rotated in the database
        await handleTokenRotation(responseData);

        // Decrypt vault fields
        responseData = await decryptResponseData(responseData);

        // Normalize response (convert PascalCase to camelCase)
        responseData = normalizeResponse(responseData);

        // Check for API failure
        if (responseData.failure !== 0) {
          handleApiFailure(responseData);
        }

        return responseData;
      } catch (error) {
        // Track failed request
        const duration = performance.now() - startTime;
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        telemetry?.trackApiCall('POST', url, undefined, duration, errorMessage);

        // Re-throw ApiClientError as-is
        if (error instanceof ApiClientError) {
          throw error;
        }

        handleHttpError(error);
      }
    });
  }

  // Auth methods
  async function login(
    email: string,
    passwordHash: string,
    sessionName = 'Session'
  ): Promise<ApiResponse> {
    await initialize();

    return requestQueue.enqueue(async () => {
      const response = await withRetry(
        () =>
          httpClient.post<ApiResponse>(
            '/CreateAuthenticationRequest',
            { name: sessionName },
            { headers: buildAuthHeaders(email, passwordHash) }
          ),
        retryConfig
      );

      let responseData = response.data;
      await handleTokenRotation(responseData);
      responseData = normalizeResponse(responseData);

      if (responseData.failure !== 0) {
        handleApiFailure(responseData);
      }

      return responseData;
    });
  }

  async function logout(): Promise<ApiResponse> {
    return makeRequest('/DeleteUserRequest', {});
  }

  async function activateUser(
    email: string,
    activationCode: string,
    passwordHash: string
  ): Promise<ApiResponse> {
    await initialize();

    return requestQueue.enqueue(async () => {
      const response = await withRetry(
        () =>
          httpClient.post<ApiResponse>(
            '/ActivateUserAccount',
            { activationCode },
            { headers: buildAuthHeaders(email, passwordHash) }
          ),
        retryConfig
      );

      let responseData = response.data;
      responseData = normalizeResponse(responseData);

      if (responseData.failure !== 0) {
        handleApiFailure(responseData);
      }

      return responseData;
    });
  }

  async function register(
    organizationName: string,
    email: string,
    passwordHash: string,
    options: {
      languagePreference?: string;
      turnstileToken?: string;
      subscriptionPlan?: string;
    } = {}
  ): Promise<ApiResponse> {
    await initialize();

    return requestQueue.enqueue(async () => {
      const response = await withRetry(
        () =>
          httpClient.post<ApiResponse>(
            '/CreateNewOrganization',
            {
              organizationName,
              userEmailAddress: email,
              languagePreference: options.languagePreference ?? DEFAULTS.LOCALE.LANGUAGE,
              subscriptionPlan: options.subscriptionPlan ?? DEFAULTS.SUBSCRIPTION.PLAN,
              turnstileToken: options.turnstileToken,
            },
            { headers: buildAuthHeaders(email, passwordHash) }
          ),
        retryConfig
      );

      let responseData = response.data;
      responseData = normalizeResponse(responseData);

      if (responseData.failure !== 0) {
        handleApiFailure(responseData);
      }

      return responseData;
    });
  }

  // Return the full client
  return {
    // CRUD methods (all POST to stored procedures)
    get: <T>(endpoint: ProcedureEndpoint, params?: Record<string, unknown>) =>
      makeRequest<T>(endpoint, params),
    post: <T>(endpoint: ProcedureEndpoint, data?: Record<string, unknown>) =>
      makeRequest<T>(endpoint, data),
    put: <T>(endpoint: ProcedureEndpoint, data?: Record<string, unknown>) =>
      makeRequest<T>(endpoint, data),
    delete: <T>(endpoint: ProcedureEndpoint, data?: Record<string, unknown>) =>
      makeRequest<T>(endpoint, data),

    // Auth methods
    login,
    logout,
    activateUser,
    register,

    // Utility methods
    updateApiUrl,
    reinitialize,
  };
}
