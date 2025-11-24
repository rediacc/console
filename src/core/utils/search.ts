/**
 * Search utilities for case-insensitive text matching
 */

/**
 * Perform case-insensitive search on a string
 * @param haystack - The string to search in
 * @param needle - The string to search for
 * @returns True if needle is found in haystack (case-insensitive)
 */
export function caseInsensitiveSearch(
  haystack: string | null | undefined,
  needle: string
): boolean {
  if (!haystack) return false;
  return haystack.toLowerCase().includes(needle.toLowerCase());
}

/**
 * Check if any of the specified fields in an item contain the search text
 * @param item - The item to search in
 * @param searchText - The text to search for
 * @param fields - Array of field names to search
 * @returns True if search text is found in any field
 */
export function searchInFields<T extends Record<string, any>>(
  item: T,
  searchText: string,
  fields: (keyof T)[]
): boolean {
  if (!searchText) return true;
  const searchLower = searchText.toLowerCase();
  return fields.some(field => {
    const value = item[field];
    if (value == null) return false;
    return String(value).toLowerCase().includes(searchLower);
  });
}

/**
 * Filter an array of items by searching multiple fields
 * @param items - Array of items to filter
 * @param searchText - The text to search for
 * @param fields - Array of field names to search
 * @returns Filtered array containing only items that match the search
 */
export function multiFieldSearch<T extends Record<string, any>>(
  items: T[],
  searchText: string,
  fields: (keyof T)[]
): T[] {
  if (!searchText) return items;
  return items.filter(item => searchInFields(item, searchText, fields));
}

/**
 * Create a search predicate function for use with Array.filter
 * @param searchText - The text to search for
 * @param fields - Array of field names to search
 * @returns A predicate function that can be used with Array.filter
 */
export function createSearchPredicate<T extends Record<string, any>>(
  searchText: string,
  fields: (keyof T)[]
): (item: T) => boolean {
  if (!searchText) return () => true;
  const searchLower = searchText.toLowerCase();
  return (item: T) =>
    fields.some(field => {
      const value = item[field];
      if (value == null) return false;
      return String(value).toLowerCase().includes(searchLower);
    });
}
