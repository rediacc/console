import { useQuery } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { parseGetCompanyDashboard, parseCompanyInfo } from '@rediacc/shared/api/parsers/company';
import type { CompanyDashboardData } from '@rediacc/shared/types';

// Lightweight query just for company info - used by MainLayout
export const useCompanyInfo = () => {
  return useQuery({
    queryKey: ['company-info'],
    queryFn: async () => {
      const response = await typedApi.GetCompanyDashboard({});
      return parseCompanyInfo(response);
    },
    staleTime: Infinity, // Never consider stale
    gcTime: Infinity, // Keep in cache forever (until logout) - gcTime replaces cacheTime in React Query v5
    refetchOnWindowFocus: false, // Don't refetch when window regains focus
    refetchOnMount: false, // Don't refetch when component mounts
    refetchOnReconnect: false, // Don't refetch when reconnecting
  });
};

export const useDashboard = () => {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: async (): Promise<CompanyDashboardData> => {
      const response = await typedApi.GetCompanyDashboard({});
      return parseGetCompanyDashboard(response);
    },
    // Remove automatic refetch - dashboard will only fetch when explicitly needed
    staleTime: 10 * 60 * 1000, // Consider data stale after 10 minutes
  });
};
