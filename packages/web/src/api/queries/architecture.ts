import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { CompanyDataGraph } from '@rediacc/shared/types';

export const useCompanyArchitecture = () => {
  return useQuery<CompanyDataGraph>({
    queryKey: ['companyArchitecture'],
    queryFn: async () => api.company.getDataGraph(),
    staleTime: 60000, // Consider data fresh for 1 minute
    refetchInterval: 300000, // Refetch every 5 minutes
  });
};
