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
 * const response = await typedApi.GetCompanyTeams();
 * const teams = extractPrimary(response);
 * ```
 */

export { createTypedApi } from './createTypedApi';
export {
  extractPrimary,
  extractFirst,
  extractByIndex,
  extractFirstByIndex,
} from './extractors';
export type {
  TypedApi,
  TypedApiConfig,
  TypedApiResponse,
  PrimaryResult,
  ResultAtIndex,
} from './types';
