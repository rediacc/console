/**
 * Array utility functions for common operations
 */

/**
 * Get unique values from an array, filtering out null/undefined
 * @param items - Array of values (may include nulls)
 * @returns Array of unique non-null values
 */
export function getUniqueValues<T>(items: (T | null | undefined)[]): T[] {
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

/**
 * Group items by a key
 * @param items - Array of items to group
 * @param keyFn - Function to extract the group key from each item
 * @returns Map of key to array of items
 */
export function groupBy<T, K extends string | number>(
  items: T[],
  keyFn: (item: T) => K
): Map<K, T[]> {
  const map = new Map<K, T[]>();
  for (const item of items) {
    const key = keyFn(item);
    const group = map.get(key);
    if (group) {
      group.push(item);
    } else {
      map.set(key, [item]);
    }
  }
  return map;
}

/**
 * Group items by a key and return as a plain object
 * @param items - Array of items to group
 * @param keyFn - Function to extract the group key from each item
 * @returns Object with keys mapping to arrays of items
 */
export function groupByToObject<T>(items: T[], keyFn: (item: T) => string): Record<string, T[]> {
  const result: Record<string, T[]> = {};
  for (const item of items) {
    const key = keyFn(item);
    if (result[key]) {
      result[key].push(item);
    } else {
      result[key] = [item];
    }
  }
  return result;
}

/**
 * Count occurrences of each unique value
 * @param items - Array of values to count
 * @returns Map of value to count
 */
export function countBy<T>(items: T[]): Map<T, number> {
  const map = new Map<T, number>();
  for (const item of items) {
    map.set(item, (map.get(item) || 0) + 1);
  }
  return map;
}

/**
 * Remove duplicates from an array based on a key function
 * @param items - Array of items
 * @param keyFn - Function to extract the unique key from each item
 * @returns Array with duplicates removed (keeps first occurrence)
 */
export function uniqueBy<T, K>(items: T[], keyFn: (item: T) => K): T[] {
  const seen = new Set<K>();
  return items.filter((item) => {
    const key = keyFn(item);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}
