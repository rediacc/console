/**
 * TypeSafeApi Factory
 *
 * Creates a proxy-based API client that provides type-safe procedure calls.
 * Each procedure is accessed as a method on the returned object.
 *
 * @example
 * ```typescript
 * const typedApi = createTypedApi(client);
 *
 * // No params required
 * const { results } = await typedApi.GetCompanyTeams();
 *
 * // With params
 * const { results } = await typedApi.GetTeamMachines({ teamName: 'Default' });
 *
 * // With config (e.g., custom headers)
 * const { results } = await typedApi.CreateAuthenticationRequest(
 *   { name: 'CLI Session' },
 *   { headers: { 'Rediacc-UserEmail': email } }
 * );
 * ```
 */

import type { TypedApi, TypedApiConfig, TypedApiResponse } from './types';
import type { StoredProcedureName } from '../../types/api-schema.generated';
import type { ApiClient } from '../services/types';
import { applyProcedureDefaults } from './defaults';

/**
 * Determines the HTTP method for a procedure based on naming conventions.
 * GET: Procedures starting with 'Get' or 'Is'
 * POST: All other procedures (Create, Update, Delete, etc.)
 */
function getHttpMethod(procedureName: string): 'get' | 'post' {
  if (procedureName.startsWith('Get') || procedureName.startsWith('Is')) {
    return 'get';
  }
  return 'post';
}

/**
 * Creates a type-safe API proxy that maps procedure names to typed API calls.
 *
 * @param client - The underlying API client (must implement ApiClient interface)
 * @returns A TypedApi proxy with methods for each stored procedure
 */
export function createTypedApi(client: ApiClient): TypedApi {
  const callerCache = new Map<string, unknown>();

  const handler: ProxyHandler<object> = {
    get(_target, prop: string | symbol) {
      if (typeof prop !== 'string') {
        return undefined;
      }

      const procedureName = prop as StoredProcedureName;

      if (callerCache.has(procedureName)) {
        return callerCache.get(procedureName);
      }

      const caller = async (
        params?: Record<string, unknown>,
        config?: TypedApiConfig
      ): Promise<TypedApiResponse<typeof procedureName>> => {
        const endpoint = `/${procedureName}` as const;
        const method = getHttpMethod(procedureName);

        // Apply procedure-specific defaults (e.g., vaultContent: '{}')
        const paramsWithDefaults = applyProcedureDefaults(procedureName, params);

        const response =
          method === 'get'
            ? await client.get(endpoint, paramsWithDefaults, config)
            : await client.post(endpoint, paramsWithDefaults, config);

        const typedResponse: TypedApiResponse<typeof procedureName> = {
          ...response,
          results: response.resultSets.map((rs) => rs.data) as TypedApiResponse<
            typeof procedureName
          >['results'],
        };
        return typedResponse;
      };

      callerCache.set(procedureName, caller);
      return caller;
    },

    set() {
      return false;
    },

    has(_target, prop: string | symbol) {
      return typeof prop === 'string';
    },
  };

  return new Proxy({}, handler) as TypedApi;
}
