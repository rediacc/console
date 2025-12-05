/**
 * Core API utilities
 * These utilities are framework-agnostic and can be used in both React and CLI
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
export function normalizeProperty<T extends object>(
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
 * Type-safe version of normalizeProperty
 *
 * @param obj - Object to extract property from
 * @param propertyNames - Array of possible property names to check
 * @returns The value of the first matching property, or null if none found
 */
export function normalizePropertyAs<T, R = unknown>(
  obj: T | null | undefined,
  ...propertyNames: string[]
): R | null {
  if (!obj || typeof obj !== 'object') return null;

  const record = obj as Record<string, unknown>;

  for (const prop of propertyNames) {
    if (record[prop] !== undefined && record[prop] !== null) {
      return record[prop] as R;
    }
  }

  return null;
}

/**
 * Normalize multiple properties at once
 *
 * @param obj - Object to extract properties from
 * @param propertyMap - Map of output keys to arrays of possible source property names
 * @returns Object with normalized properties
 *
 * @example
 * const normalized = normalizeProperties(apiResponse, {
 *   taskId: ['taskId', 'TaskId', 'task_id'],
 *   status: ['status', 'Status'],
 *   retryCount: ['retryCount', 'RetryCount', 'retry_count']
 * })
 */
export function normalizeProperties<T extends object>(
  obj: T | null | undefined,
  propertyMap: Record<string, string[]>
): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  for (const [outputKey, propertyNames] of Object.entries(propertyMap)) {
    result[outputKey] = normalizeProperty(obj, ...propertyNames);
  }

  return result;
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

/**
 * Check if an object has any of the specified properties
 *
 * @param obj - Object to check
 * @param propertyNames - Array of property names to check for
 * @returns True if any property exists and is not null/undefined
 */
export function hasProperty<T extends object>(
  obj: T | null | undefined,
  ...propertyNames: string[]
): boolean {
  if (!obj) return false;

  const record = obj as Record<string, unknown>;
  for (const prop of propertyNames) {
    if (record[prop] !== undefined && record[prop] !== null) {
      return true;
    }
  }

  return false;
}

/**
 * Deep get a nested property using dot notation
 *
 * @param obj - Object to extract property from
 * @param path - Dot-separated path to the property
 * @returns Value at the path or undefined
 *
 * @example
 * const value = getNestedProperty(response, 'data.user.name')
 */
export function getNestedProperty<T = unknown>(
  obj: Record<string, unknown> | null | undefined,
  path: string
): T | undefined {
  if (!obj) return undefined;

  const keys = path.split('.');
  let current: unknown = obj;

  for (const key of keys) {
    if (current === null || current === undefined || typeof current !== 'object') {
      return undefined;
    }
    current = (current as Record<string, unknown>)[key];
  }

  return current as T;
}
