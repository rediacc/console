/**
 * Property normalization utilities for API responses
 * Handles different casing conventions (camelCase, PascalCase, etc.)
 */

/**
 * Normalize property names from API responses
 * Handles different casing conventions (camelCase, PascalCase, etc.)
 *
 * @param obj - Object to extract property from
 * @param propertyNames - Array of possible property names to check
 * @returns The value of the first matching property, or null if none found
 *
 * @example
 * const result = normalizeProperty(apiResponse, 'taskId', 'TaskId', 'task_id')
 * // Returns the value if any of those properties exist
 */
function normalizeProperty<T extends object>(
  obj: T | null | undefined,
  ...propertyNames: string[]
): unknown {
  if (!obj) return null;

  const record = obj as Record<string, unknown>;
  for (const prop of propertyNames) {
    if (record[prop] !== undefined && record[prop] !== null) {
      return record[prop];
    }
  }

  return null;
}

/**
 * Get a property value with type coercion to string
 *
 * @param obj - Object to extract property from
 * @param propertyNames - Array of possible property names to check
 * @returns String value or empty string if not found
 */
export function normalizeToString<T extends object>(
  obj: T | null | undefined,
  ...propertyNames: string[]
): string {
  const value = normalizeProperty(obj, ...propertyNames);
  if (value === null || value === undefined) return '';
  return String(value);
}

/**
 * Get a property value with type coercion to number
 *
 * @param obj - Object to extract property from
 * @param defaultValue - Default value if not found or not a number
 * @param propertyNames - Array of possible property names to check
 * @returns Number value or default if not found
 */
export function normalizeToNumber<T extends object>(
  obj: T | null | undefined,
  defaultValue: number,
  ...propertyNames: string[]
): number {
  const value = normalizeProperty(obj, ...propertyNames);
  if (value === null || value === undefined) return defaultValue;
  const num = Number(value);
  return isNaN(num) ? defaultValue : num;
}

/**
 * Get a property value with type coercion to boolean
 *
 * @param obj - Object to extract property from
 * @param propertyNames - Array of possible property names to check
 * @returns Boolean value (false if not found)
 */
export function normalizeToBoolean<T extends object>(
  obj: T | null | undefined,
  ...propertyNames: string[]
): boolean {
  const value = normalizeProperty(obj, ...propertyNames);
  return Boolean(value);
}
