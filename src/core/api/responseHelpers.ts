import { extractTableData, getFirstRow } from './response'
import type { ApiResponse } from '@/core/types/api'

/**
 * Handle API response with standardized error checking
 * Throws an error if the response indicates failure
 *
 * @example
 * const clusters = handleApiResponse<Cluster[]>(response, 'Failed to fetch clusters')
 */
export function handleApiResponse<T>(
  response: ApiResponse,
  errorMessage: string,
  tableIndex = 1,
  defaultValue: T | [] = []
): T {
  if (response.failure !== 0) {
    throw new Error(response.errors?.join(', ') || errorMessage)
  }

  return extractTableData<T>(response, tableIndex, defaultValue as T) as T
}

/**
 * Handle API response and extract first row
 * Useful for single-item queries
 *
 * @example
 * const status = handleApiResponseFirstRow<Status>(response, 'Failed to fetch status')
 */
export function handleApiResponseFirstRow<T>(
  response: ApiResponse,
  errorMessage: string,
  tableIndex = 0
): T | null {
  if (response.failure !== 0) {
    throw new Error(response.errors?.join(', ') || errorMessage)
  }

  return getFirstRow<T>(response, tableIndex) ?? null
}

/**
 * Check if API response indicates success
 * Does not throw, returns boolean
 */
export function isApiSuccess(response: ApiResponse): boolean {
  return response.failure === 0
}

/**
 * Extract error message from API response
 */
export function getApiError(response: ApiResponse, fallback: string): string {
  return response.errors?.join(', ') || fallback
}
