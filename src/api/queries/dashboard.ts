import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../client';

interface CompanyInfo {
  CompanyName: string;
  StripeCustomerId: string | null;
}

interface ActiveSubscription {
  Edition: string;
  PlanName: string;
  PlanDescription: string;
  Quantity: number;
  TotalActivePurchases: number;
  StartDate: string;
  EndDate: string;
  DaysRemaining: number;
  Status: string;
  IsActive: number;
  IsTrial: number;
  IsExpiringSoon: number;
  AutoRenew: boolean;
}

interface BillingInfo {
  Price: number;
  Currency: string;
  BillingInterval: string;
  IntervalCount: number;
  StripePriceId: string;
}

interface AvailablePlan {
  PlanCode: string;
  PlanName: string;
  Description: string;
  MaxUsers: number;
  DefaultPrice: number;
  Currency: string;
  IsCurrentPlan: number;
}

interface ResourceLimit {
  ResourceType: string;
  ResourceLimit: number;
  ActiveSubscriptionTier: string;
  CurrentUsage: number;
  IsLimitReached: number;
  UsagePercentage: number;
  PlanComparison: Array<{
    PlanCode: string;
    PlanName: string;
    Limit: number;
  }>;
}

interface AccountHealth {
  ResourcesAtLimit: number;
  ResourcesNearLimit: number;
  SubscriptionStatus: 'Critical' | 'Warning' | 'Good';
  UpgradeRecommendation: string;
}

interface FeatureAccess {
  HasAdvancedAnalytics: number;
  HasPrioritySupport: number;
  HasDedicatedAccount: number;
  HasCustomBranding: number;
}

interface SubscriptionDetail {
  planCode: string;
  planName: string;
  quantity: number;
  startDate: string;
  endDate: string;
  daysRemaining: number;
  status: string;
  stripeSubscriptionId: string | null;
  isTrial: number;
}

interface DashboardData {
  companyInfo: CompanyInfo;
  activeSubscription: ActiveSubscription | null;
  billingInfo: BillingInfo | null;
  availablePlans: AvailablePlan[];
  resources: ResourceLimit[];
  accountHealth: AccountHealth;
  featureAccess: FeatureAccess;
  allActiveSubscriptions?: SubscriptionDetail[];
}

export const useDashboard = () => {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const response = await apiClient.post('/GetCompanyDashboardJson', {});
      
      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch dashboard data');
      }
      
      // Look for the data in the second result set
      if (!response.tables?.[1]?.data?.[0]?.subscriptionAndResourcesJson) {
        throw new Error('Invalid dashboard data format');
      }
      
      const jsonData = response.tables[1].data[0].subscriptionAndResourcesJson;
      
      // Parse the main JSON string
      const parsedData = typeof jsonData === 'string' ? JSON.parse(jsonData) : jsonData;
      
      // Parse nested JSON strings
      if (typeof parsedData.companyInfo === 'string') {
        parsedData.companyInfo = JSON.parse(parsedData.companyInfo);
      }
      if (typeof parsedData.activeSubscription === 'string') {
        parsedData.activeSubscription = JSON.parse(parsedData.activeSubscription);
      }
      if (typeof parsedData.billingInfo === 'string') {
        parsedData.billingInfo = JSON.parse(parsedData.billingInfo);
      }
      if (typeof parsedData.accountHealth === 'string') {
        parsedData.accountHealth = JSON.parse(parsedData.accountHealth);
      }
      if (typeof parsedData.featureAccess === 'string') {
        parsedData.featureAccess = JSON.parse(parsedData.featureAccess);
      }
      
      // Check if there's a second result set with all active subscriptions
      if (response.tables?.[2]?.data) {
        parsedData.allActiveSubscriptions = response.tables[2].data;
      }
      
      return parsedData as DashboardData;
    },
    refetchInterval: 5 * 60 * 1000, // Refetch every 5 minutes
    staleTime: 2 * 60 * 1000, // Consider data stale after 2 minutes
  });
};