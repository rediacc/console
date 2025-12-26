/**
 * TypeSafeApi Type Definitions
 *
 * Provides type-safe API calling through a proxy pattern that maps
 * procedure names directly to typed API calls.
 */

import type { ApiResponse } from '../../types/api';
import type {
  StoredProcedureName,
  ProcedureParamsMap,
  ProcedureResultsMap,
} from '../../types/api-schema.generated';

/**
 * Check if a type is an empty record (Record<string, never>)
 * Used to detect procedures that require no parameters
 */
type IsEmptyRecord<T> = [keyof T] extends [never] ? true : false;

/**
 * Configuration options for individual API calls
 */
export interface TypedApiConfig {
  headers?: Record<string, string>;
  timeout?: number;
  [key: string]: unknown;
}

/**
 * For procedures with no params, make the params argument optional.
 * For procedures with params, require the params argument.
 */
type ParamsArg<P extends StoredProcedureName> = IsEmptyRecord<
  ProcedureParamsMap[P]
> extends true
  ? [params?: ProcedureParamsMap[P], config?: TypedApiConfig]
  : [params: ProcedureParamsMap[P], config?: TypedApiConfig];

/**
 * Typed API response with result sets properly typed as tuples.
 * Extends ApiResponse to maintain compatibility with parsers that expect resultSets.
 */
export interface TypedApiResponse<P extends StoredProcedureName> extends ApiResponse {
  /** Typed results as a tuple matching the procedure's result sets */
  results: ProcedureResultsMap[P];
}

/**
 * A procedure caller function with proper parameter and return types
 */
type ProcedureCaller<P extends StoredProcedureName> = (
  ...args: ParamsArg<P>
) => Promise<TypedApiResponse<P>>;

/**
 * The TypedApi interface - maps each procedure name to a typed caller
 */
export type TypedApi = {
  [P in StoredProcedureName]: ProcedureCaller<P>;
};

/**
 * Extract the primary data type from a procedure's results
 */
export type PrimaryResult<P extends StoredProcedureName> =
  ProcedureResultsMap[P] extends [unknown, infer Second, ...unknown[]]
    ? Second extends (infer U)[]
      ? U
      : never
    : ProcedureResultsMap[P] extends [infer First, ...unknown[]]
      ? First extends (infer U)[]
        ? U
        : never
      : never;

/**
 * Extract result set by index
 */
export type ResultAtIndex<
  P extends StoredProcedureName,
  I extends number,
> = ProcedureResultsMap[P] extends readonly unknown[]
  ? ProcedureResultsMap[P][I] extends (infer U)[]
    ? U
    : never
  : never;
