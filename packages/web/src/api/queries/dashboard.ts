import { useQuery } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { extractFirstByIndex } from '@rediacc/shared/api/typedApi';
import type {
  CompanyDashboardData,
  GetCompanyDashboardJson_ResultSet1,
} from '@rediacc/shared/types';

// Lightweight query just for company info - used by MainLayout
export const useCompanyInfo = () => {
  return useQuery({
    queryKey: ['company-info'],
    queryFn: async () => {
      const response = await typedApi.GetCompanyDashboardJson({});
      const data =
        extractFirstByIndex<GetCompanyDashboardJson_ResultSet1>(response, 1) ??
        extractFirstByIndex<GetCompanyDashboardJson_ResultSet1>(response, 0);
      if (!data?.subscriptionAndResourcesJson) throw new Error('No dashboard data returned');
      // Parse the JSON field which contains the subscription and resources data
      const fullData = JSON.parse(data.subscriptionAndResourcesJson) as CompanyDashboardData;
      return {
        companyInfo: fullData.companyInfo,
        activeSubscription: fullData.activeSubscription,
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
    queryFn: async (): Promise<CompanyDashboardData> => {
      const response = await typedApi.GetCompanyDashboardJson({});
      const data =
        extractFirstByIndex<GetCompanyDashboardJson_ResultSet1>(response, 1) ??
        extractFirstByIndex<GetCompanyDashboardJson_ResultSet1>(response, 0);
      if (!data?.subscriptionAndResourcesJson) throw new Error('No dashboard data returned');
      // The JSON field contains the full dashboard data
      return JSON.parse(data.subscriptionAndResourcesJson) as CompanyDashboardData;
    },
    // Remove automatic refetch - dashboard will only fetch when explicitly needed
    staleTime: 10 * 60 * 1000, // Consider data stale after 10 minutes
  });
};
