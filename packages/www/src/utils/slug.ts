/**
 * Convert a string to a URL-friendly slug
 * @param str - The string to convert
 * @returns A lowercase, hyphenated slug
 */
function stringToSlug(str: string): string {
  return str
    .toLowerCase()
    .trim()
    .replaceAll(/[^\w\s-]/g, '') // Remove special characters
    .replaceAll(/\s+/g, '-') // Replace spaces with hyphens
    .replaceAll(/-+/g, '-'); // Replace multiple hyphens with single hyphen
}

/**
 * Generate an anchor ID for a problem section
 * @param pageSlug - The page slug (e.g., 'system-portability', 'disaster-recovery')
 * @param sectionNumber - The section number (1, 2, 3, etc.)
 * @param sectionTitle - The section title
 * @returns A unique anchor ID
 */
export function generateSectionAnchorId(
  pageSlug: string,
  sectionNumber: number,
  sectionTitle: string
): string {
  const titleSlug = stringToSlug(sectionTitle);
  return `${pageSlug}-${sectionNumber}-${titleSlug}`;
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
