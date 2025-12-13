/**
 * Helper utilities for generating consistent data-testid attributes
 * Used to ensure stable e2e test selectors across the application
 */

/**
 * Formats a route key for use in data-testid attributes
 * Converts "/machines/repositories" to "machines-repositories"
 *
 * @param key - The route key (typically starts with /)
 * @returns Formatted string suitable for data-testid
 */
export const formatKeyForTestId = (key: string): string =>
  key.replace(/\//g, '-').replace(/^-/, '');
