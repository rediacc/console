/**
 * Extract base slug from a content collection slug (removes language prefix)
 * @param slug - The full slug (e.g., 'en/getting-started' or 'getting-started')
 * @returns The base slug without language prefix
 */
export function getBaseSlug(slug: string): string {
  const parts = slug.split('/');
  return parts.length > 1 ? parts[parts.length - 1] : slug;
}
