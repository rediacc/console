/**
 * Search utilities for case-insensitive text matching
 */

/**
 * Check if any of the specified fields in an item contain the search text
 * @param item - The item to search in
 * @param searchText - The text to search for
 * @param fields - Array of field names to search
 * @returns True if search text is found in any field
 */
export function searchInFields<T extends object>(
  item: T,
  searchText: string,
  fields: (keyof T)[]
): boolean {
  if (!searchText) return true;
  const searchLower = searchText.toLowerCase();
  return fields.some((field) => {
    const value = item[field];
    if (value == null) return false;
    return String(value).toLowerCase().includes(searchLower);
  });
}
