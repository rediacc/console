/**
 * Shared Auth Service
 *
 * Factory function that creates auth-specific API methods.
 * These methods require special HTTP headers (Rediacc-UserEmail, Rediacc-UserHash)
 * instead of the normal request token authentication.
 */

import type { ApiResponse } from '../../types/api';

/**
 * Low-level HTTP client interface for auth operations.
 * This is a subset of what axios provides, allowing both web and CLI clients to work.
 */
export interface AuthHttpClient {
  post<T = unknown>(
    url: string,
    data?: unknown,
    config?: { headers?: Record<string, string> }
  ): Promise<{ data: T }>;
}

/**
 * Auth service interface with methods that require special HTTP headers.
 */
export interface AuthService {
  /**
   * Create an authentication session (login).
   * @param email User's email address
   * @param passwordHash Hashed password
   * @param sessionName Optional session name (default: 'Session')
   */
  login(email: string, passwordHash: string, sessionName?: string): Promise<ApiResponse>;

  /**
   * Activate a user account.
   * @param email User's email address
   * @param activationCode Activation code received during registration
   * @param passwordHash Hashed password for the new account
   */
  activateUser(email: string, activationCode: string, passwordHash: string): Promise<ApiResponse>;

  /**
   * Register a new organization and user.
   * @param organizationName Organization name
   * @param email User's email address
   * @param passwordHash Hashed password
   * @param plan Optional subscription plan (default: 'COMMUNITY')
   * @param language Optional language preference (default: 'en')
   */
  register(
    organizationName: string,
    email: string,
    passwordHash: string,
    plan?: string,
    language?: string
  ): Promise<ApiResponse>;
}

/**
 * Build auth headers for requests that authenticate via email/password hash.
 */
function buildAuthHeaders(email: string, passwordHash: string): Record<string, string> {
  return {
    'Rediacc-UserEmail': email,
    'Rediacc-UserHash': passwordHash,
  };
}

/**
 * Create an auth service instance.
 *
 * @param client HTTP client (axios instance or compatible)
 * @param apiPrefix API path prefix (e.g., '/StoredProcedure')
 * @returns AuthService instance
 *
 * @example
 * // Web usage
 * const authApi = createAuthService(axiosInstance, '/StoredProcedure');
 *
 * // CLI usage
 * const authApi = createAuthService(axiosInstance, '/StoredProcedure');
 */
export function createAuthService(client: AuthHttpClient, apiPrefix = ''): AuthService {
  const buildUrl = (endpoint: string) => `${apiPrefix}${endpoint}`;

  return {
    async login(email, passwordHash, sessionName = 'Session') {
      const response = await client.post<ApiResponse>(
        buildUrl('/CreateAuthenticationRequest'),
        { name: sessionName },
        { headers: buildAuthHeaders(email, passwordHash) }
      );
      return response.data;
    },

    async activateUser(email, activationCode, passwordHash) {
      const response = await client.post<ApiResponse>(
        buildUrl('/ActivateUserAccount'),
        { activationCode },
        { headers: buildAuthHeaders(email, passwordHash) }
      );
      return response.data;
    },

    async register(organizationName, email, passwordHash, plan = 'COMMUNITY', language = 'en') {
      const response = await client.post<ApiResponse>(
        buildUrl('/CreateNewOrganization'),
        {
          organizationName,
          userEmailAddress: email,
          subscriptionPlan: plan,
          languagePreference: language,
        },
        { headers: buildAuthHeaders(email, passwordHash) }
      );
      return response.data;
    },
  };
}
