/**
 * Result Extraction Utilities
 *
 * Helper functions to extract typed data from TypedApiResponse objects.
 */

import type { PrimaryResult, TypedApiResponse } from './types';
import type { StoredProcedureName } from '../../types/api-schema.generated';

/**
 * Extract the primary data array from a typed response.
 * For most procedures, this is index 1 (after the nextRequestToken set).
 */
export function extractPrimary<P extends StoredProcedureName>(
  response: TypedApiResponse<P>,
  options: { fallbackIndex?: number } = {}
): PrimaryResult<P>[] {
  const { fallbackIndex = 0 } = options;
  const results = response.results as unknown[][];

  if (results[1]?.length > 0) {
    return results[1] as PrimaryResult<P>[];
  }

  if (results[fallbackIndex]) {
    return results[fallbackIndex] as PrimaryResult<P>[];
  }

  return [];
}

/**
 * Extract the first item from the primary result set.
 */
export function extractFirst<P extends StoredProcedureName>(
  response: TypedApiResponse<P>,
  options: { fallbackIndex?: number } = {}
): PrimaryResult<P> | null {
  const items = extractPrimary(response, options);
  return items.length > 0 ? items[0] : null;
}

/**
 * Extract result set by index.
 */
export function extractByIndex<T>(
  response: TypedApiResponse<StoredProcedureName>,
  index: number
): T[] {
  const results = response.results as unknown[][];
  return (results[index] ?? []) as T[];
}

/**
 * Extract first item from result set by index.
 */
export function extractFirstByIndex<T>(
  response: TypedApiResponse<StoredProcedureName>,
  index: number
): T | null {
  const items = extractByIndex<T>(response, index);
  return items.length > 0 ? items[0] : null;
}
