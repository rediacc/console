import type { ApiResponse } from '../types/api';

/**
 * Extract a single error message from an API response.
 * Checks multiple locations in priority order:
 * 1. errors array (SQL RAISERROR messages)
 * 2. message field
 * 3. Nested resultSets[0].data[0] error fields
 */
export function extractErrorMessage(response: ApiResponse): string {
  // Check errors array first (SQL RAISERROR messages)
  if (response.errors.length > 0) {
    return response.errors.join('; ');
  }

  // Check message field
  if (response.message) {
    return response.message;
  }

  // Check nested resultSet messages
  const nested = response.resultSets[0]?.data[0] as Record<string, unknown> | undefined;
  if (nested) {
    const nestedMsg = nested.errorMessage ?? nested.ErrorMessage ?? nested.error ?? nested.message;
    if (typeof nestedMsg === 'string' && nestedMsg) {
      return nestedMsg;
    }
  }

  return 'Request failed';
}

/**
 * Extract all error messages from an API response.
 * Collects errors from multiple sources without duplicates.
 */
export function extractApiErrors(response: ApiResponse): string[] {
  const errors: string[] = [];

  // From errors array (SQL RAISERROR messages)
  if (response.errors.length) {
    errors.push(...response.errors);
  }

  // Check resultSets for error messages
  for (const rs of response.resultSets) {
    for (const row of rs.data as Record<string, unknown>[]) {
      const errorMsg = row.errorMessage ?? row.ErrorMessage ?? row.error;
      if (typeof errorMsg === 'string' && errorMsg && !errors.includes(errorMsg)) {
        errors.push(errorMsg);
      }
    }
  }

  return errors;
}

/**
 * Get primary error message with fallback to failure code.
 */
export function getPrimaryErrorMessage(response: ApiResponse): string {
  const errors = extractApiErrors(response);
  return errors[0] || response.message || `Request failed (code: ${response.failure})`;
}
