/**
 * Services Module Exports
 *
 * This module exports types and the auth service factory.
 * The general API service factory (createApiServices) has been replaced
 * by the TypeSafeApi proxy pattern (typedApi).
 */

export type { ApiClient, ApiRequestConfig, ProcedureEndpoint } from './types';
export { createAuthService } from './auth';
export type { AuthService, AuthHttpClient } from './auth';
