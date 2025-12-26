import { useQuery } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { extractFirstByIndex } from '@rediacc/shared/api';
import type { CompanyDropdownData } from '@rediacc/shared/types';

const EMPTY_DROPDOWN_DATA: CompanyDropdownData = {
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

export const useDropdownData = (context?: string) => {
  return useQuery({
    queryKey: ['dropdown-data', context],
    queryFn: async () => {
      const response = await typedApi.GetLookupData(context ? { context } : {});
      const row = extractFirstByIndex<{ dropdownValues?: string | null }>(response as never, 1) ??
        extractFirstByIndex<{ dropdownValues?: string | null }>(response as never, 0);
      if (row?.dropdownValues) {
        try {
          const parsed = JSON.parse(row.dropdownValues) as Partial<CompanyDropdownData>;
          return { ...EMPTY_DROPDOWN_DATA, ...parsed };
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
