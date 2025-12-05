import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { CompanyDashboardData } from '@rediacc/shared/types';

// Lightweight query just for company info - used by MainLayout
export const useCompanyInfo = () => {
  return useQuery({
    queryKey: ['company-info'],
    queryFn: async () => {
      const data = await api.company.getDashboard();
      return {
        companyInfo: data.companyInfo,
        activeSubscription: data.activeSubscription,
      };
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
    queryFn: async (): Promise<CompanyDashboardData> => api.company.getDashboard(),
    // Remove automatic refetch - dashboard will only fetch when explicitly needed
    staleTime: 10 * 60 * 1000, // Consider data stale after 10 minutes
  });
};
