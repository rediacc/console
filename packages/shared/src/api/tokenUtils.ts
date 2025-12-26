import type { ApiResponse } from '../types/api';

/**
 * Extract nextRequestToken from API response.
 * Token is always in resultSets[0].data[0].nextRequestToken
 */
export function extractNextToken(response: ApiResponse): string | null {
  if (response.resultSets.length === 0) return null;
  const firstResultSet = response.resultSets[0];
  if (!firstResultSet.data.length) return null;

  const row = firstResultSet.data[0] as Record<string, unknown>;
  const token = row.nextRequestToken;

  return typeof token === 'string' && token ? token : null;
}
