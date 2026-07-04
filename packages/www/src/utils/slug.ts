/**
 * Convert a string to a URL-friendly slug
 * @param str - The string to convert
 * @returns A lowercase, hyphenated slug
 */
export function stringToSlug(str: string): string {
  return str
    .toLowerCase()
    .trim()
    .replaceAll(/[^\w\s-]/g, '') // Remove special characters
    .replaceAll(/\s+/g, '-') // Replace spaces with hyphens
    .replaceAll(/-+/g, '-'); // Replace multiple hyphens with single hyphen
}

/**
 * Extract base slug from a content collection slug (removes language prefix)
 * @param slug - The full slug (e.g., 'en/getting-started' or 'getting-started')
 * @returns The base slug without language prefix
 */
export function getBaseSlug(slug: string): string {
  const parts = slug.split('/');
  return parts.length > 1 ? parts[parts.length - 1] : slug;
}
