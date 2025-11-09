/**
 * Path utilities for displaying and formatting file system paths
 */

/**
 * Abbreviates a long path by showing "..." at the beginning
 * Keeps the last portion of the path visible for readability
 *
 * @param path - The full path to abbreviate
 * @param maxLength - Maximum length before abbreviation (default: 50)
 * @returns Abbreviated path with "..." prefix if needed
 *
 * @example
 * abbreviatePath('/very/long/path/to/file.txt', 20)
 * // Returns: '.../path/to/file.txt'
 */
export const abbreviatePath = (path: string, maxLength: number = 50): string => {
  if (!path || path.length <= maxLength) return path

  // Show last portion of path with ellipsis
  const truncated = '...' + path.slice(-(maxLength - 3))
  return truncated
}
