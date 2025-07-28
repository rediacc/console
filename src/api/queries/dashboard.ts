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

interface QueueTeamIssue {
  TeamName: string;
  TotalItems: number;
  PendingItems: number;
  ActiveItems: number;
  StaleItems: number;
}

interface QueueMachineIssue {
  MachineName: string;
  TeamName: string;
  BridgeName: string;
  TotalItems: number;
  PendingItems: number;
  ActiveItems: number;
  StaleItems: number;
}

interface QueueStats {
  PendingCount: number;
  AssignedCount: number;
  ProcessingCount: number;
  ActiveCount: number;
  CompletedCount: number;
  CancelledCount: number;
  FailedCount: number;
  TotalCount: number;
  StaleCount: number;
  CompletedToday: number;
  CancelledToday: number;
  FailedToday: number;
  CreatedToday: number;
  OldestPendingAgeMinutes: number;
  AvgPendingAgeMinutes: number;
  HighestPriorityPending: number | null;
  HighPriorityPending: number | null;
  NormalPriorityPending: number | null;
  LowPriorityPending: number | null;
  HasStaleItems: number;
  HasOldPendingItems: number;
  TeamIssues: QueueTeamIssue[] | string;
  MachineIssues: QueueMachineIssue[] | string;
}

interface DistributedStorageTeamBreakdown {
  TeamName: string;
  TotalMachines: number;
  AvailableMachines: number;
  ClusterMachines: number;
  ImageMachines: number;
  CloneMachines: number;
}

interface DistributedStorageStats {
  total_machines: number;
  available_machines: number;
  cluster_assigned_machines: number;
  image_assigned_machines: number;
  clone_assigned_machines: number;
  truly_available_machines: number;
  available_percentage: number;
  cluster_percentage: number;
  image_percentage: number;
  clone_percentage: number;
  total_clusters: number;
  active_clusters: number;
  avg_machines_per_cluster: number;
  team_breakdown: DistributedStorageTeamBreakdown[] | string;
}

interface DashboardData {
  companyInfo: CompanyInfo;
  activeSubscription: ActiveSubscription | null;
  billingInfo: BillingInfo | null;
  availablePlans: AvailablePlan[];
  resources: ResourceLimit[];
  accountHealth: AccountHealth;
  featureAccess: FeatureAccess;
  queueStats?: QueueStats;
  distributedStorageStats?: DistributedStorageStats;
  allActiveSubscriptions?: SubscriptionDetail[];
}

// Lightweight query just for company info - used by MainLayout
export const useCompanyInfo = () => {
  return useQuery({
    queryKey: ['company-info'],
    queryFn: async () => {
      const response = await apiClient.post('/GetCompanyDashboardJson', {});
      
      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch company info');
      }
      
      // Look for the data in the second result set
      if (!response.resultSets?.[1]?.data?.[0]?.subscriptionAndResourcesJson) {
        throw new Error('Invalid dashboard data format');
      }
      
      const jsonData = response.resultSets[1].data[0].subscriptionAndResourcesJson;
      
      // Parse the main JSON string
      const parsedData = typeof jsonData === 'string' ? JSON.parse(jsonData) : jsonData;
      
      // Parse only what we need for the layout
      const companyInfo = typeof parsedData.companyInfo === 'string' 
        ? JSON.parse(parsedData.companyInfo) 
        : parsedData.companyInfo;
        
      const activeSubscription = typeof parsedData.activeSubscription === 'string' 
        ? JSON.parse(parsedData.activeSubscription) 
        : parsedData.activeSubscription;
      
      return { companyInfo, activeSubscription };
    },
    staleTime: Infinity, // Never consider stale
    cacheTime: Infinity, // Keep in cache forever (until logout)
    refetchOnWindowFocus: false, // Don't refetch when window regains focus
    refetchOnMount: false, // Don't refetch when component mounts
    refetchOnReconnect: false, // Don't refetch when reconnecting
  });
};

export const useDashboard = () => {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const response = await apiClient.post('/GetCompanyDashboardJson', {});
      
      if (response.failure !== 0) {
        throw new Error(response.errors?.join(', ') || 'Failed to fetch dashboard data');
      }
      
      // Look for the data in the second result set
      if (!response.resultSets?.[1]?.data?.[0]?.subscriptionAndResourcesJson) {
        throw new Error('Invalid dashboard data format');
      }
      
      const jsonData = response.resultSets[1].data[0].subscriptionAndResourcesJson;
      
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
      if (typeof parsedData.queueStats === 'string') {
        parsedData.queueStats = JSON.parse(parsedData.queueStats);
        
        // Parse nested JSON arrays in queueStats
        if (parsedData.queueStats) {
          if (typeof parsedData.queueStats.TeamIssues === 'string') {
            parsedData.queueStats.TeamIssues = JSON.parse(parsedData.queueStats.TeamIssues);
          }
          if (typeof parsedData.queueStats.MachineIssues === 'string') {
            parsedData.queueStats.MachineIssues = JSON.parse(parsedData.queueStats.MachineIssues);
          }
        }
      }
      if (typeof parsedData.distributedStorageStats === 'string') {
        parsedData.distributedStorageStats = JSON.parse(parsedData.distributedStorageStats);
        
        // Parse nested JSON arrays in distributedStorageStats
        if (parsedData.distributedStorageStats) {
          if (typeof parsedData.distributedStorageStats.team_breakdown === 'string') {
            parsedData.distributedStorageStats.team_breakdown = JSON.parse(parsedData.distributedStorageStats.team_breakdown);
          }
        }
      }
      
      // Check if there's a second result set with all active subscriptions
      if (response.resultSets?.[2]?.data) {
        parsedData.allActiveSubscriptions = response.resultSets[2].data;
      }
      
      return parsedData as DashboardData;
    },
    // Remove automatic refetch - dashboard will only fetch when explicitly needed
    staleTime: 10 * 60 * 1000, // Consider data stale after 10 minutes
  });
};