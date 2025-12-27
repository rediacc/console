/**
 * Base Extraction Utilities
 */

import type { ApiResponse } from '../../types/api';

export function extractRowsByIndex<T>(response: ApiResponse, index: number): T[] {
  const resultSet = response.resultSets[index] as { data: T[] } | undefined;
  if (!resultSet) return [];
  return resultSet.data;
}

export function extractFirstByIndex<T>(response: ApiResponse, index: number): T | null {
  const rows = extractRowsByIndex<T>(response, index);
  return rows.length > 0 ? rows[0] : null;
}

export function extractPrimaryOrSecondary<T>(response: ApiResponse<T>): T[] {
  const secondary = response.resultSets[1]?.data;
  if (Array.isArray(secondary) && secondary.length > 0) {
    return secondary;
  }
  const primary = response.resultSets[0]?.data;
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- primary may be undefined at runtime
  if (!primary) return [];
  return primary;
}

export function toBoolean(value: unknown): boolean {
  return value === true || value === 1 || value === '1' || value === 'true';
}

export function safeJsonParse<T>(value: string, fallback: T): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}
