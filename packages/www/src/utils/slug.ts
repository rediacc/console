/**
 * Convert a string to a URL-friendly slug
 * @param str - The string to convert
 * @returns A lowercase, hyphenated slug
 */
export function stringToSlug(str: string): string {
  return str
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '') // Remove special characters
    .replace(/\s+/g, '-') // Replace spaces with hyphens
    .replace(/-+/g, '-'); // Replace multiple hyphens with single hyphen
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
