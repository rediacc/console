import { configService } from '../services/config-resources.js';

/**
 * Build a resolver that maps repository GUIDs to friendly names.
 * Returns the original value if no mapping exists.
 */
export function createGuidResolver(guidMap: Record<string, string>): (guid: string) => string {
  return (guid: string) => {
    const entry = guidMap[guid];
    if (!entry) return guid;
    return entry.endsWith(':latest') ? entry.slice(0, -7) : entry;
  };
}

/**
 * Resolve GUID fields to human-readable names.
 *
 * For guidField='name': renames `name` → `guid`, adds `name` with resolved value.
 * For other fields (e.g. 'repository'): renames field → `{field}_guid`, overwrites field with resolved value.
 */
export function resolveGuids<T>(
  items: T[],
  resolve: (guid: string) => string,
  guidField: keyof T & string = 'name' as keyof T & string
): T[] {
  const guidRename = guidField === 'name' ? 'guid' : `${guidField}_guid`;
  return items.map((item) => {
    const guidValue = String(item[guidField]);
    const spread = { ...item };
    const result = spread as Record<string, unknown>;
    result[guidField] = resolve(guidValue);
    result[guidRename] = guidValue;
    return result as T;
  });
}

export async function loadGuidMap(): Promise<Record<string, string>> {
  try {
    return await configService.getRepositoryGuidMap();
  } catch {
    return {};
  }
}
