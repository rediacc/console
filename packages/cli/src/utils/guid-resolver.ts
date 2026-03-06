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

export async function loadGuidMap(): Promise<Record<string, string>> {
  try {
    return await configService.getRepositoryGuidMap();
  } catch {
    return {};
  }
}
