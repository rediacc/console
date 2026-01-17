/**
 * TypeSafeApi Module
 *
 * Provides a type-safe proxy-based API client for calling stored procedures.
 *
 * @example
 * ```typescript
 * import { createTypedApi, extractPrimary } from '@rediacc/shared/api/typedApi';
 *
 * const typedApi = createTypedApi(client);
 * const response = await typedApi.GetOrganizationTeams();
 * const teams = extractPrimary(response);
 * ```
 */

export { type CreateTypedApiOptions, createTypedApi } from './createTypedApi';
export { applyProcedureDefaults, PROCEDURE_DEFAULTS } from './defaults';
export {
  extractByIndex,
  extractFirst,
  extractFirstByIndex,
  extractPrimary,
} from './extractors';
export type {
  PrimaryResult,
  ResultAtIndex,
  TypedApi,
  TypedApiConfig,
  TypedApiResponse,
} from './types';
