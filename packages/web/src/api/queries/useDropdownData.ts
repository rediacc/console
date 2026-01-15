import { extractFirstByIndex } from '@rediacc/shared/api';
import type { OrganizationDropdownData } from '@rediacc/shared/types';
import { useQuery } from '@tanstack/react-query';
import { typedApi } from '@/api/client';

const EMPTY_DROPDOWN_DATA: OrganizationDropdownData = {
  teams: [],
  allTeams: [],
  regions: [],
  machines: [],
  bridges: [],
  bridgesByRegion: [],
  machinesByTeam: [],
  users: [],
  permissionGroups: [],
  permissions: [],
  subscriptionPlans: [],
};

const DROPDOWN_KEYS = [
  'teams',
  'allTeams',
  'regions',
  'machines',
  'bridges',
  'bridgesByRegion',
  'machinesByTeam',
  'users',
  'permissionGroups',
  'permissions',
  'subscriptionPlans',
] as const satisfies readonly (keyof OrganizationDropdownData)[];

function ensureArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value : [];
}

/**
 * Safely merges parsed dropdown data with defaults, ensuring arrays are never null.
 * This prevents runtime errors like "users.filter is not a function" when API returns null.
 */
function mergeDropdownData(parsed: Partial<OrganizationDropdownData>): OrganizationDropdownData {
  const result = { ...EMPTY_DROPDOWN_DATA };
  for (const key of DROPDOWN_KEYS) {
    (result as Record<string, unknown[]>)[key] = ensureArray(parsed[key]);
  }
  return result as OrganizationDropdownData;
}

export const useDropdownData = (context?: string) => {
  return useQuery({
    queryKey: ['dropdown-data', context],
    queryFn: async () => {
      const response = await typedApi.GetLookupData(context ? { context } : {});
      const row =
        extractFirstByIndex<{ dropdownValues?: string | null }>(response as never, 1) ??
        extractFirstByIndex<{ dropdownValues?: string | null }>(response as never, 0);
      if (row?.dropdownValues) {
        try {
          const parsed = JSON.parse(row.dropdownValues) as Partial<OrganizationDropdownData>;
          return mergeDropdownData(parsed);
        } catch {
          return EMPTY_DROPDOWN_DATA;
        }
      }
      return EMPTY_DROPDOWN_DATA;
    },
    staleTime: 30 * 60 * 1000, // 30 minutes
    gcTime: 60 * 60 * 1000, // 1 hour
  });
};
