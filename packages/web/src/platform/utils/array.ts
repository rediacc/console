/**
 * Array utility functions for common operations
 */

/**
 * Get unique values from an array, filtering out null/undefined
 * @param items - Array of values (may include nulls)
 * @returns Array of unique non-null values
 */
function getUniqueValues<T>(items: (T | null | undefined)[]): T[] {
  return [...new Set(items.filter((item): item is T => item != null))];
}

/**
 * Get unique values by mapping items first
 * @param items - Array of items to map
 * @param mapper - Function to extract the value from each item
 * @returns Array of unique non-null mapped values
 */
export function getUniqueMappedValues<T, K>(
  items: T[],
  mapper: (item: T) => K | null | undefined
): K[] {
  return getUniqueValues(items.map(mapper));
}
