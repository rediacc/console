import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
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
      const data = await api.company.getLookupData(context ? { context } : undefined);
      return { ...EMPTY_DROPDOWN_DATA, ...data };
    },
    staleTime: 30 * 60 * 1000, // 30 minutes
    gcTime: 60 * 60 * 1000, // 1 hour
  });
};
