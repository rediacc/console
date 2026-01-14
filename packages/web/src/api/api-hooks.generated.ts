/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * Generated from: middleware/AppData/stored-procedures.json
 * Configuration: packages/web/src/api/hooks.config.json
 * Generated at: 2026-01-14T09:22:04Z
 * Schema version: 3.0.0
 *
 * To regenerate, run: ./go deploy prep
 * Or directly: dotnet run -- --generate-hooks
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import { parseResponse } from '@rediacc/shared/api';
import { parseGetAuditLogs, parseGetEntityAuditTrace } from '@rediacc/shared/api/parsers/audit';
import { parseGetOrganizationDashboard } from '@rediacc/shared/api/parsers/organization';
import { parseGetQueueItemTrace, parseGetTeamQueueItems } from '@rediacc/shared/api/parsers/queue';
import type {
  AuditTraceResponse,
  GetAuditLogs_ResultSet1,
  GetAvailableMachinesForClone_ResultSet1,
  GetCephClusterMachines_ResultSet1,
  GetCephClusters_ResultSet1,
  GetCephPools_ResultSet1,
  GetCephRbdClones_ResultSet1,
  GetCephRbdImages_ResultSet1,
  GetCephRbdSnapshots_ResultSet1,
  GetCloneMachineAssignmentValidation_ResultSet1,
  GetCloneMachines_ResultSet1,
  GetEntityHistory_ResultSet1,
  GetLookupData_ResultSet1,
  GetMachineAssignmentStatus_ResultSet1,
  GetOrganizationPermissionGroups_ResultSet1,
  GetOrganizationRegions_ResultSet1,
  GetOrganizationTeams_ResultSet1,
  GetOrganizationUsers_ResultSet1,
  GetOrganizationVault_ResultSet1,
  GetPermissionGroupDetails_ResultSet1,
  GetRegionBridges_ResultSet1,
  GetRequestAuthenticationStatus_ResultSet1,
  GetSystemConfiguration_ResultSet0,
  GetTeamMachines_ResultSet1,
  GetTeamMembers_ResultSet1,
  GetTeamRepositories_ResultSet1,
  GetTeamStorages_ResultSet1,
  GetUserOrganization_ResultSet1,
  GetUserRequests_ResultSet1,
  GetUserVault_ResultSet1,
  IsRegistered_ResultSet0,
  OrganizationDashboardData,
  QueueListResult,
  QueueTrace,
} from '@rediacc/shared/types';
import { getInvalidationKeys, getMessages, getQueryOptions } from './hooks.config';
import {
  ensureVaultContent,
  hashPassword,
  type CreateBridgeInput,
  type CreateCephClusterInput,
  type CreateMachineInput,
  type CreateRegionInput,
  type CreateRepositoryInput,
  type CreateStorageInput,
  type CreateTeamInput,
  type CreateUserInput,
} from './mutation-transforms';

// ============================================================================
// Generated Query Keys
// ============================================================================

export const GENERATED_QUERY_KEYS = {
  auditLogs: (startDate?: string, endDate?: string, entityFilter?: string, maxRecords?: number) => ['auditLogs', startDate, endDate, entityFilter, maxRecords] as const,
  availableMachinesForClone: (teamName: string) => ['availableMachinesForClone', teamName] as const,
  cephClusterMachines: (clusterName: string) => ['cephClusterMachines', clusterName] as const,
  cephClusters: ['cephClusters'] as const,
  cephPools: (teamName?: string, clusterName?: string) => ['cephPools', teamName, clusterName] as const,
  cephRbdClones: (snapshotName?: string, imageName?: string, poolName?: string, teamName?: string) => ['cephRbdClones', snapshotName, imageName, poolName, teamName] as const,
  cephRbdImages: (poolName?: string, teamName?: string) => ['cephRbdImages', poolName, teamName] as const,
  cephRbdSnapshots: (imageName?: string, poolName?: string, teamName?: string) => ['cephRbdSnapshots', imageName, poolName, teamName] as const,
  cloneMachineAssignmentValidation: (teamName: string, machineNames: string) => ['cloneMachineAssignmentValidation', teamName, machineNames] as const,
  cloneMachines: (cloneName: string, snapshotName: string, imageName: string, poolName: string, teamName: string) => ['cloneMachines', cloneName, snapshotName, imageName, poolName, teamName] as const,
  entityAuditTrace: (entityType: string, entityIdentifier: string) => ['entityAuditTrace', entityType, entityIdentifier] as const,
  entityHistory: (entity: string, credential: string, maxRecords?: number) => ['entityHistory', entity, credential, maxRecords] as const,
  lookupData: (context?: string) => ['lookupData', context] as const,
  machineAssignmentStatus: (machineName: string, teamName: string) => ['machineAssignmentStatus', machineName, teamName] as const,
  organizationDashboard: ['organizationDashboard'] as const,
  organizationPermissionGroups: ['organizationPermissionGroups'] as const,
  organizationRegions: ['organizationRegions'] as const,
  organizationTeams: ['organizationTeams'] as const,
  organizationUsers: ['organizationUsers'] as const,
  organizationVault: ['organizationVault'] as const,
  permissionGroupDetails: (permissionGroupName: string) => ['permissionGroupDetails', permissionGroupName] as const,
  queueItemTrace: (taskId: string) => ['queueItemTrace', taskId] as const,
  regionBridges: (regionName: string) => ['regionBridges', regionName] as const,
  requestAuthenticationStatus: ['requestAuthenticationStatus'] as const,
  systemConfiguration: (configKey?: string) => ['systemConfiguration', configKey] as const,
  teamMachines: (teamName?: string) => ['teamMachines', teamName] as const,
  teamMembers: (teamName?: string) => ['teamMembers', teamName] as const,
  teamQueueItems: (teamName?: string, machineName?: string, bridgeName?: string, status?: string, priority?: number, minPriority?: number, maxPriority?: number, dateFrom?: string, dateTo?: string, taskId?: string, includeCompleted?: boolean, includeCancelled?: boolean, onlyStale?: boolean, staleThresholdMinutes?: number, maxRecords?: number, createdByUserEmail?: string) => ['teamQueueItems', teamName, machineName, bridgeName, status, priority, minPriority, maxPriority, dateFrom, dateTo, taskId, includeCompleted, includeCancelled, onlyStale, staleThresholdMinutes, maxRecords, createdByUserEmail] as const,
  teamRepositories: (teamName?: string) => ['teamRepositories', teamName] as const,
  teamStorages: (teamName?: string) => ['teamStorages', teamName] as const,
  userOrganization: ['userOrganization'] as const,
  userRequests: ['userRequests'] as const,
  userVault: ['userVault'] as const,
  registered: (userName: string) => ['registered', userName] as const,
} as const;

// ============================================================================
// Generated Query Hooks
// ============================================================================

export const useGetAuditLogs = (startDate?: string, endDate?: string, entityFilter?: string, maxRecords?: number) => {
  return useQuery<GetAuditLogs_ResultSet1[]>({
    queryKey: ['auditLogs'],
    queryFn: async () => {
      const response = await typedApi.GetAuditLogs({ startDate, endDate, entityFilter, maxRecords });
      return parseGetAuditLogs(response as never);
    },
    staleTime: 30000,
    gcTime: 300000,
  });
};

export const useGetAvailableMachinesForClone = (teamName: string) => {
  const options = getQueryOptions('GetAvailableMachinesForClone');
  return useQuery<GetAvailableMachinesForClone_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.availableMachinesForClone(teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetAvailableMachinesForClone({ teamName });
      return parseResponse(response as never);
    },
    enabled: !!teamName,
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetCephClusterMachines = (clusterName: string) => {
  const options = getQueryOptions('GetCephClusterMachines');
  return useQuery<GetCephClusterMachines_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.cephClusterMachines(clusterName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetCephClusterMachines({ clusterName });
      return parseResponse(response as never);
    },
    enabled: !!clusterName,
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetCephClusters = () => {
  const options = getQueryOptions('GetCephClusters');
  return useQuery<GetCephClusters_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.cephClusters,
    queryFn: async () => {
      const response = await typedApi.GetCephClusters({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetCephPools = (teamName?: string, clusterName?: string) => {
  const options = getQueryOptions('GetCephPools');
  return useQuery<GetCephPools_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.cephPools(teamName ?? '', clusterName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetCephPools({ teamName, clusterName });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetCephRbdClones = (snapshotName?: string, imageName?: string, poolName?: string, teamName?: string) => {
  const options = getQueryOptions('GetCephRbdClones');
  return useQuery<GetCephRbdClones_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.cephRbdClones(snapshotName ?? '', imageName ?? '', poolName ?? '', teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetCephRbdClones({ snapshotName, imageName, poolName, teamName });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetCephRbdImages = (poolName?: string, teamName?: string) => {
  const options = getQueryOptions('GetCephRbdImages');
  return useQuery<GetCephRbdImages_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.cephRbdImages(poolName ?? '', teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetCephRbdImages({ poolName, teamName });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetCephRbdSnapshots = (imageName?: string, poolName?: string, teamName?: string) => {
  const options = getQueryOptions('GetCephRbdSnapshots');
  return useQuery<GetCephRbdSnapshots_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.cephRbdSnapshots(imageName ?? '', poolName ?? '', teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetCephRbdSnapshots({ imageName, poolName, teamName });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetCloneMachineAssignmentValidation = (teamName: string, machineNames: string) => {
  const options = getQueryOptions('GetCloneMachineAssignmentValidation');
  return useQuery<GetCloneMachineAssignmentValidation_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.cloneMachineAssignmentValidation(teamName ?? '', machineNames ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetCloneMachineAssignmentValidation({ teamName, machineNames });
      return parseResponse(response as never);
    },
    enabled: !!teamName && !!machineNames,
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetCloneMachines = (cloneName: string, snapshotName: string, imageName: string, poolName: string, teamName: string) => {
  const options = getQueryOptions('GetCloneMachines');
  return useQuery<GetCloneMachines_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.cloneMachines(cloneName ?? '', snapshotName ?? '', imageName ?? '', poolName ?? '', teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetCloneMachines({ cloneName, snapshotName, imageName, poolName, teamName });
      return parseResponse(response as never);
    },
    enabled: !!cloneName && !!snapshotName && !!imageName && !!poolName && !!teamName,
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetEntityAuditTrace = (entityType: string, entityIdentifier: string) => {
  return useQuery<AuditTraceResponse>({
    queryKey: ['entityAuditTrace', entityType, entityIdentifier],
    queryFn: async () => {
      const response = await typedApi.GetEntityAuditTrace({ entityType, entityIdentifier });
      return parseGetEntityAuditTrace(response as never);
    },
    enabled: !!entityType && !!entityIdentifier,
    staleTime: 30000,
    gcTime: 300000,
  });
};

export const useGetEntityHistory = (entity: string, credential: string, maxRecords?: number) => {
  const options = getQueryOptions('GetEntityHistory');
  return useQuery<GetEntityHistory_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.entityHistory(entity ?? '', credential ?? '', maxRecords),
    queryFn: async () => {
      const response = await typedApi.GetEntityHistory({ entity, credential, maxRecords });
      return parseResponse(response as never);
    },
    enabled: !!entity && !!credential,
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetLookupData = (context?: string) => {
  const options = getQueryOptions('GetLookupData');
  return useQuery<GetLookupData_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.lookupData(context ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetLookupData({ context });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetMachineAssignmentStatus = (machineName: string, teamName: string) => {
  const options = getQueryOptions('GetMachineAssignmentStatus');
  return useQuery<GetMachineAssignmentStatus_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.machineAssignmentStatus(machineName ?? '', teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetMachineAssignmentStatus({ machineName, teamName });
      return parseResponse(response as never);
    },
    enabled: !!machineName && !!teamName,
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetOrganizationDashboard = () => {
  return useQuery<OrganizationDashboardData>({
    queryKey: ['organization', 'dashboard'],
    queryFn: async () => {
      const response = await typedApi.GetOrganizationDashboard({});
      return parseGetOrganizationDashboard(response as never);
    },
    staleTime: 60000,
  });
};

export const useGetOrganizationPermissionGroups = () => {
  const options = getQueryOptions('GetOrganizationPermissionGroups');
  return useQuery<GetOrganizationPermissionGroups_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.organizationPermissionGroups,
    queryFn: async () => {
      const response = await typedApi.GetOrganizationPermissionGroups({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetOrganizationRegions = () => {
  const options = getQueryOptions('GetOrganizationRegions');
  return useQuery<GetOrganizationRegions_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.organizationRegions,
    queryFn: async () => {
      const response = await typedApi.GetOrganizationRegions({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetOrganizationTeams = () => {
  const options = getQueryOptions('GetOrganizationTeams');
  return useQuery<GetOrganizationTeams_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.organizationTeams,
    queryFn: async () => {
      const response = await typedApi.GetOrganizationTeams({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetOrganizationUsers = () => {
  const options = getQueryOptions('GetOrganizationUsers');
  return useQuery<GetOrganizationUsers_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.organizationUsers,
    queryFn: async () => {
      const response = await typedApi.GetOrganizationUsers({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetOrganizationVault = () => {
  const options = getQueryOptions('GetOrganizationVault');
  return useQuery<GetOrganizationVault_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.organizationVault,
    queryFn: async () => {
      const response = await typedApi.GetOrganizationVault({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetPermissionGroupDetails = (permissionGroupName: string) => {
  const options = getQueryOptions('GetPermissionGroupDetails');
  return useQuery<GetPermissionGroupDetails_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.permissionGroupDetails(permissionGroupName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetPermissionGroupDetails({ permissionGroupName });
      return parseResponse(response as never);
    },
    enabled: !!permissionGroupName,
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetQueueItemTrace = (taskId: string) => {
  return useQuery<QueueTrace>({
    queryKey: ['queue', 'trace', taskId],
    queryFn: async () => {
      const response = await typedApi.GetQueueItemTrace({ taskId });
      return parseGetQueueItemTrace(response as never);
    },
    enabled: !!taskId,
    staleTime: 5000,
    refetchInterval: 5000,
  });
};

export const useGetRegionBridges = (regionName: string) => {
  const options = getQueryOptions('GetRegionBridges');
  return useQuery<GetRegionBridges_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.regionBridges(regionName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetRegionBridges({ regionName });
      return parseResponse(response as never);
    },
    enabled: !!regionName,
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetRequestAuthenticationStatus = () => {
  const options = getQueryOptions('GetRequestAuthenticationStatus');
  return useQuery<GetRequestAuthenticationStatus_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.requestAuthenticationStatus,
    queryFn: async () => {
      const response = await typedApi.GetRequestAuthenticationStatus({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetSystemConfiguration = (configKey?: string) => {
  const options = getQueryOptions('GetSystemConfiguration');
  return useQuery<GetSystemConfiguration_ResultSet0[]>({
    queryKey: GENERATED_QUERY_KEYS.systemConfiguration(configKey ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetSystemConfiguration({ configKey });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetTeamMachines = (teamName?: string) => {
  const options = getQueryOptions('GetTeamMachines');
  return useQuery<GetTeamMachines_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.teamMachines(teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetTeamMachines({ teamName });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetTeamMembers = (teamName?: string) => {
  const options = getQueryOptions('GetTeamMembers');
  return useQuery<GetTeamMembers_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.teamMembers(teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetTeamMembers({ teamName });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetTeamQueueItems = (teamName?: string, machineName?: string, bridgeName?: string, status?: string, priority?: number, minPriority?: number, maxPriority?: number, dateFrom?: string, dateTo?: string, taskId?: string, includeCompleted?: boolean, includeCancelled?: boolean, onlyStale?: boolean, staleThresholdMinutes?: number, maxRecords?: number, createdByUserEmail?: string) => {
  return useQuery<QueueListResult>({
    queryKey: ['queue', 'items', teamName],
    queryFn: async () => {
      const response = await typedApi.GetTeamQueueItems({ teamName, machineName, bridgeName, status, priority, minPriority, maxPriority, dateFrom, dateTo, taskId, includeCompleted, includeCancelled, onlyStale, staleThresholdMinutes, maxRecords, createdByUserEmail });
      return parseGetTeamQueueItems(response as never);
    },
    enabled: !!teamName,
    staleTime: 30000,
  });
};

export const useGetTeamRepositories = (teamName?: string) => {
  const options = getQueryOptions('GetTeamRepositories');
  return useQuery<GetTeamRepositories_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.teamRepositories(teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetTeamRepositories({ teamName });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetTeamStorages = (teamName?: string) => {
  const options = getQueryOptions('GetTeamStorages');
  return useQuery<GetTeamStorages_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.teamStorages(teamName ?? ''),
    queryFn: async () => {
      const response = await typedApi.GetTeamStorages({ teamName });
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetUserOrganization = () => {
  const options = getQueryOptions('GetUserOrganization');
  return useQuery<GetUserOrganization_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.userOrganization,
    queryFn: async () => {
      const response = await typedApi.GetUserOrganization({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetUserRequests = () => {
  const options = getQueryOptions('GetUserRequests');
  return useQuery<GetUserRequests_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.userRequests,
    queryFn: async () => {
      const response = await typedApi.GetUserRequests({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useGetUserVault = () => {
  const options = getQueryOptions('GetUserVault');
  return useQuery<GetUserVault_ResultSet1[]>({
    queryKey: GENERATED_QUERY_KEYS.userVault,
    queryFn: async () => {
      const response = await typedApi.GetUserVault({});
      return parseResponse(response as never);
    },
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

export const useIsRegistered = (userName: string) => {
  const options = getQueryOptions('IsRegistered');
  return useQuery<IsRegistered_ResultSet0[]>({
    queryKey: GENERATED_QUERY_KEYS.registered(userName ?? ''),
    queryFn: async () => {
      const response = await typedApi.IsRegistered({ userName });
      return parseResponse(response as never);
    },
    enabled: !!userName,
    staleTime: options?.staleTime ?? 30000,
    ...(options?.refetchInterval && { refetchInterval: options.refetchInterval }),
  });
};

// ============================================================================
// Generated Mutation Hooks (Type-Safe with Semantic Input Types)
// ============================================================================

export const useCancelQueueItem = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CancelQueueItem');
  const invalidationKeys = getInvalidationKeys('CancelQueueItem');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CancelQueueItem',
    mutationFn: (params) => typedApi.CancelQueueItem(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateBridge = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateBridge');
  const invalidationKeys = getInvalidationKeys('CreateBridge');

  return useMutationWithFeedback<unknown, Error, CreateBridgeInput>({
    procedureName: 'CreateBridge',
    mutationFn: (input) => {
      const params = {
        regionName: input.regionName,
        bridgeName: input.bridgeName,
        vaultContent: ensureVaultContent(input.vaultContent),
      };
      return typedApi.CreateBridge(params);
    },
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateCephCluster = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateCephCluster');
  const invalidationKeys = getInvalidationKeys('CreateCephCluster');

  return useMutationWithFeedback<unknown, Error, CreateCephClusterInput>({
    procedureName: 'CreateCephCluster',
    mutationFn: (input) => {
      const params = {
        clusterName: input.clusterName,
        vaultContent: ensureVaultContent(input.vaultContent),
      };
      return typedApi.CreateCephCluster(params);
    },
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateCephPool = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateCephPool');
  const invalidationKeys = getInvalidationKeys('CreateCephPool');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CreateCephPool',
    mutationFn: (params) => typedApi.CreateCephPool(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateCephRbdClone = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateCephRbdClone');
  const invalidationKeys = getInvalidationKeys('CreateCephRbdClone');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CreateCephRbdClone',
    mutationFn: (params) => typedApi.CreateCephRbdClone(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateCephRbdImage = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateCephRbdImage');
  const invalidationKeys = getInvalidationKeys('CreateCephRbdImage');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CreateCephRbdImage',
    mutationFn: (params) => typedApi.CreateCephRbdImage(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateCephRbdSnapshot = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateCephRbdSnapshot');
  const invalidationKeys = getInvalidationKeys('CreateCephRbdSnapshot');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CreateCephRbdSnapshot',
    mutationFn: (params) => typedApi.CreateCephRbdSnapshot(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateMachine = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateMachine');
  const invalidationKeys = getInvalidationKeys('CreateMachine');

  return useMutationWithFeedback<unknown, Error, CreateMachineInput>({
    procedureName: 'CreateMachine',
    mutationFn: (input) => {
      const params = {
        teamName: input.teamName,
        machineName: input.machineName,
        bridgeName: input.bridgeName,
        vaultContent: ensureVaultContent(input.vaultContent),
      };
      return typedApi.CreateMachine(params);
    },
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateNewOrganization = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateNewOrganization');
  const invalidationKeys = getInvalidationKeys('CreateNewOrganization');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CreateNewOrganization',
    mutationFn: (params) => typedApi.CreateNewOrganization(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateNewUser = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateNewUser');
  const invalidationKeys = getInvalidationKeys('CreateNewUser');

  return useMutationWithFeedback<unknown, Error, CreateUserInput>({
    procedureName: 'CreateNewUser',
    mutationFn: async (input) => {
      const params = {
        newUserEmail: input.email,
        newUserHash: await hashPassword(input.password),
      };
      return typedApi.CreateNewUser(params);
    },
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreatePermissionGroup = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreatePermissionGroup');
  const invalidationKeys = getInvalidationKeys('CreatePermissionGroup');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CreatePermissionGroup',
    mutationFn: (params) => typedApi.CreatePermissionGroup(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreatePermissionInGroup = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreatePermissionInGroup');
  const invalidationKeys = getInvalidationKeys('CreatePermissionInGroup');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CreatePermissionInGroup',
    mutationFn: (params) => typedApi.CreatePermissionInGroup(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateQueueItem = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateQueueItem');
  const invalidationKeys = getInvalidationKeys('CreateQueueItem');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CreateQueueItem',
    mutationFn: (params) => typedApi.CreateQueueItem(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateRegion = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateRegion');
  const invalidationKeys = getInvalidationKeys('CreateRegion');

  return useMutationWithFeedback<unknown, Error, CreateRegionInput>({
    procedureName: 'CreateRegion',
    mutationFn: (input) => {
      const params = {
        regionName: input.regionName,
        vaultContent: ensureVaultContent(input.vaultContent),
      };
      return typedApi.CreateRegion(params);
    },
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateRepository = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateRepository');
  const invalidationKeys = getInvalidationKeys('CreateRepository');

  return useMutationWithFeedback<unknown, Error, CreateRepositoryInput>({
    procedureName: 'CreateRepository',
    mutationFn: (input) => {
      const params = {
        teamName: input.teamName,
        repositoryName: input.repositoryName,
        repositoryTag: input.repositoryTag ?? 'latest',
        parentRepositoryName: input.parentRepositoryName,
        repositoryGuid: input.repositoryGuid,
        networkMode: input.networkMode,
        vaultContent: ensureVaultContent(input.vaultContent),
      };
      return typedApi.CreateRepository(params);
    },
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateStorage = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateStorage');
  const invalidationKeys = getInvalidationKeys('CreateStorage');

  return useMutationWithFeedback<unknown, Error, CreateStorageInput>({
    procedureName: 'CreateStorage',
    mutationFn: (input) => {
      const params = {
        teamName: input.teamName,
        storageName: input.storageName,
        vaultContent: ensureVaultContent(input.vaultContent),
      };
      return typedApi.CreateStorage(params);
    },
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateTeam = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateTeam');
  const invalidationKeys = getInvalidationKeys('CreateTeam');

  return useMutationWithFeedback<unknown, Error, CreateTeamInput>({
    procedureName: 'CreateTeam',
    mutationFn: (input) => {
      const params = {
        teamName: input.teamName,
        vaultContent: ensureVaultContent(input.vaultContent),
      };
      return typedApi.CreateTeam(params);
    },
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useCreateTeamMembership = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('CreateTeamMembership');
  const invalidationKeys = getInvalidationKeys('CreateTeamMembership');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'CreateTeamMembership',
    mutationFn: (params) => typedApi.CreateTeamMembership(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteBridge = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteBridge');
  const invalidationKeys = getInvalidationKeys('DeleteBridge');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteBridge',
    mutationFn: (params) => typedApi.DeleteBridge(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteCephCluster = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteCephCluster');
  const invalidationKeys = getInvalidationKeys('DeleteCephCluster');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteCephCluster',
    mutationFn: (params) => typedApi.DeleteCephCluster(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteCephPool = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteCephPool');
  const invalidationKeys = getInvalidationKeys('DeleteCephPool');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteCephPool',
    mutationFn: (params) => typedApi.DeleteCephPool(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteCephRbdClone = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteCephRbdClone');
  const invalidationKeys = getInvalidationKeys('DeleteCephRbdClone');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteCephRbdClone',
    mutationFn: (params) => typedApi.DeleteCephRbdClone(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteCephRbdImage = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteCephRbdImage');
  const invalidationKeys = getInvalidationKeys('DeleteCephRbdImage');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteCephRbdImage',
    mutationFn: (params) => typedApi.DeleteCephRbdImage(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteCephRbdSnapshot = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteCephRbdSnapshot');
  const invalidationKeys = getInvalidationKeys('DeleteCephRbdSnapshot');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteCephRbdSnapshot',
    mutationFn: (params) => typedApi.DeleteCephRbdSnapshot(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteMachine = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteMachine');
  const invalidationKeys = getInvalidationKeys('DeleteMachine');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteMachine',
    mutationFn: (params) => typedApi.DeleteMachine(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeletePermissionFromGroup = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeletePermissionFromGroup');
  const invalidationKeys = getInvalidationKeys('DeletePermissionFromGroup');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeletePermissionFromGroup',
    mutationFn: (params) => typedApi.DeletePermissionFromGroup(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeletePermissionGroup = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeletePermissionGroup');
  const invalidationKeys = getInvalidationKeys('DeletePermissionGroup');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeletePermissionGroup',
    mutationFn: (params) => typedApi.DeletePermissionGroup(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteQueueItem = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteQueueItem');
  const invalidationKeys = getInvalidationKeys('DeleteQueueItem');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteQueueItem',
    mutationFn: (params) => typedApi.DeleteQueueItem(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteRegion = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteRegion');
  const invalidationKeys = getInvalidationKeys('DeleteRegion');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteRegion',
    mutationFn: (params) => typedApi.DeleteRegion(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteRepository = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteRepository');
  const invalidationKeys = getInvalidationKeys('DeleteRepository');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteRepository',
    mutationFn: (params) => typedApi.DeleteRepository(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteStorage = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteStorage');
  const invalidationKeys = getInvalidationKeys('DeleteStorage');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteStorage',
    mutationFn: (params) => typedApi.DeleteStorage(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteTeam = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteTeam');
  const invalidationKeys = getInvalidationKeys('DeleteTeam');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteTeam',
    mutationFn: (params) => typedApi.DeleteTeam(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteUserFromTeam = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteUserFromTeam');
  const invalidationKeys = getInvalidationKeys('DeleteUserFromTeam');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteUserFromTeam',
    mutationFn: (params) => typedApi.DeleteUserFromTeam(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useDeleteUserRequest = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('DeleteUserRequest');
  const invalidationKeys = getInvalidationKeys('DeleteUserRequest');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'DeleteUserRequest',
    mutationFn: (params) => typedApi.DeleteUserRequest(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useForkAuthenticationRequest = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('ForkAuthenticationRequest');
  const invalidationKeys = getInvalidationKeys('ForkAuthenticationRequest');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'ForkAuthenticationRequest',
    mutationFn: (params) => typedApi.ForkAuthenticationRequest(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const usePrivilegeAuthenticationRequest = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('PrivilegeAuthenticationRequest');
  const invalidationKeys = getInvalidationKeys('PrivilegeAuthenticationRequest');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'PrivilegeAuthenticationRequest',
    mutationFn: (params) => typedApi.PrivilegeAuthenticationRequest(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const usePromoteRepositoryToGrand = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('PromoteRepositoryToGrand');
  const invalidationKeys = getInvalidationKeys('PromoteRepositoryToGrand');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'PromoteRepositoryToGrand',
    mutationFn: (params) => typedApi.PromoteRepositoryToGrand(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useResetBridgeAuthorization = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('ResetBridgeAuthorization');
  const invalidationKeys = getInvalidationKeys('ResetBridgeAuthorization');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'ResetBridgeAuthorization',
    mutationFn: (params) => typedApi.ResetBridgeAuthorization(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useRetryFailedQueueItem = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('RetryFailedQueueItem');
  const invalidationKeys = getInvalidationKeys('RetryFailedQueueItem');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'RetryFailedQueueItem',
    mutationFn: (params) => typedApi.RetryFailedQueueItem(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateBridgeName = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateBridgeName');
  const invalidationKeys = getInvalidationKeys('UpdateBridgeName');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateBridgeName',
    mutationFn: (params) => typedApi.UpdateBridgeName(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateBridgeVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateBridgeVault');
  const invalidationKeys = getInvalidationKeys('UpdateBridgeVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateBridgeVault',
    mutationFn: (params) => typedApi.UpdateBridgeVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateCephClusterVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateCephClusterVault');
  const invalidationKeys = getInvalidationKeys('UpdateCephClusterVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateCephClusterVault',
    mutationFn: (params) => typedApi.UpdateCephClusterVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateCephPoolVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateCephPoolVault');
  const invalidationKeys = getInvalidationKeys('UpdateCephPoolVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateCephPoolVault',
    mutationFn: (params) => typedApi.UpdateCephPoolVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateCloneMachineAssignments = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateCloneMachineAssignments');
  const invalidationKeys = getInvalidationKeys('UpdateCloneMachineAssignments');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateCloneMachineAssignments',
    mutationFn: (params) => typedApi.UpdateCloneMachineAssignments(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateCloneMachineRemovals = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateCloneMachineRemovals');
  const invalidationKeys = getInvalidationKeys('UpdateCloneMachineRemovals');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateCloneMachineRemovals',
    mutationFn: (params) => typedApi.UpdateCloneMachineRemovals(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateImageMachineAssignment = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateImageMachineAssignment');
  const invalidationKeys = getInvalidationKeys('UpdateImageMachineAssignment');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateImageMachineAssignment',
    mutationFn: (params) => typedApi.UpdateImageMachineAssignment(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateMachineAssignedBridge = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateMachineAssignedBridge');
  const invalidationKeys = getInvalidationKeys('UpdateMachineAssignedBridge');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateMachineAssignedBridge',
    mutationFn: (params) => typedApi.UpdateMachineAssignedBridge(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateMachineCeph = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateMachineCeph');
  const invalidationKeys = getInvalidationKeys('UpdateMachineCeph');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateMachineCeph',
    mutationFn: (params) => typedApi.UpdateMachineCeph(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateMachineClusterAssignment = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateMachineClusterAssignment');
  const invalidationKeys = getInvalidationKeys('UpdateMachineClusterAssignment');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateMachineClusterAssignment',
    mutationFn: (params) => typedApi.UpdateMachineClusterAssignment(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateMachineClusterRemoval = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateMachineClusterRemoval');
  const invalidationKeys = getInvalidationKeys('UpdateMachineClusterRemoval');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateMachineClusterRemoval',
    mutationFn: (params) => typedApi.UpdateMachineClusterRemoval(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateMachineName = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateMachineName');
  const invalidationKeys = getInvalidationKeys('UpdateMachineName');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateMachineName',
    mutationFn: (params) => typedApi.UpdateMachineName(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateMachineStatus = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateMachineStatus');
  const invalidationKeys = getInvalidationKeys('UpdateMachineStatus');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateMachineStatus',
    mutationFn: (params) => typedApi.UpdateMachineStatus(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateMachineVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateMachineVault');
  const invalidationKeys = getInvalidationKeys('UpdateMachineVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateMachineVault',
    mutationFn: (params) => typedApi.UpdateMachineVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateOrganizationVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateOrganizationVault');
  const invalidationKeys = getInvalidationKeys('UpdateOrganizationVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateOrganizationVault',
    mutationFn: (params) => typedApi.UpdateOrganizationVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateQueueItemResponse = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateQueueItemResponse');
  const invalidationKeys = getInvalidationKeys('UpdateQueueItemResponse');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateQueueItemResponse',
    mutationFn: (params) => typedApi.UpdateQueueItemResponse(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateQueueItemToCompleted = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateQueueItemToCompleted');
  const invalidationKeys = getInvalidationKeys('UpdateQueueItemToCompleted');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateQueueItemToCompleted',
    mutationFn: (params) => typedApi.UpdateQueueItemToCompleted(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateRegionName = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateRegionName');
  const invalidationKeys = getInvalidationKeys('UpdateRegionName');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateRegionName',
    mutationFn: (params) => typedApi.UpdateRegionName(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateRegionVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateRegionVault');
  const invalidationKeys = getInvalidationKeys('UpdateRegionVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateRegionVault',
    mutationFn: (params) => typedApi.UpdateRegionVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateRepositoryName = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateRepositoryName');
  const invalidationKeys = getInvalidationKeys('UpdateRepositoryName');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateRepositoryName',
    mutationFn: (params) => typedApi.UpdateRepositoryName(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateRepositoryTag = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateRepositoryTag');
  const invalidationKeys = getInvalidationKeys('UpdateRepositoryTag');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateRepositoryTag',
    mutationFn: (params) => typedApi.UpdateRepositoryTag(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateRepositoryVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateRepositoryVault');
  const invalidationKeys = getInvalidationKeys('UpdateRepositoryVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateRepositoryVault',
    mutationFn: (params) => typedApi.UpdateRepositoryVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateStorageName = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateStorageName');
  const invalidationKeys = getInvalidationKeys('UpdateStorageName');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateStorageName',
    mutationFn: (params) => typedApi.UpdateStorageName(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateStorageVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateStorageVault');
  const invalidationKeys = getInvalidationKeys('UpdateStorageVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateStorageVault',
    mutationFn: (params) => typedApi.UpdateStorageVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateTeamName = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateTeamName');
  const invalidationKeys = getInvalidationKeys('UpdateTeamName');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateTeamName',
    mutationFn: (params) => typedApi.UpdateTeamName(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateTeamVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateTeamVault');
  const invalidationKeys = getInvalidationKeys('UpdateTeamVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateTeamVault',
    mutationFn: (params) => typedApi.UpdateTeamVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateUserAssignedPermissions = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateUserAssignedPermissions');
  const invalidationKeys = getInvalidationKeys('UpdateUserAssignedPermissions');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateUserAssignedPermissions',
    mutationFn: (params) => typedApi.UpdateUserAssignedPermissions(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateUserEmail = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateUserEmail');
  const invalidationKeys = getInvalidationKeys('UpdateUserEmail');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateUserEmail',
    mutationFn: (params) => typedApi.UpdateUserEmail(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateUserLanguage = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateUserLanguage');
  const invalidationKeys = getInvalidationKeys('UpdateUserLanguage');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateUserLanguage',
    mutationFn: (params) => typedApi.UpdateUserLanguage(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateUserPassword = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateUserPassword');
  const invalidationKeys = getInvalidationKeys('UpdateUserPassword');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateUserPassword',
    mutationFn: (params) => typedApi.UpdateUserPassword(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateUserTFA = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateUserTFA');
  const invalidationKeys = getInvalidationKeys('UpdateUserTFA');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateUserTFA',
    mutationFn: (params) => typedApi.UpdateUserTFA(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateUserToActivated = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateUserToActivated');
  const invalidationKeys = getInvalidationKeys('UpdateUserToActivated');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateUserToActivated',
    mutationFn: (params) => typedApi.UpdateUserToActivated(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateUserToDeactivated = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateUserToDeactivated');
  const invalidationKeys = getInvalidationKeys('UpdateUserToDeactivated');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateUserToDeactivated',
    mutationFn: (params) => typedApi.UpdateUserToDeactivated(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

export const useUpdateUserVault = () => {
  const queryClient = useQueryClient();
  const messages = getMessages('UpdateUserVault');
  const invalidationKeys = getInvalidationKeys('UpdateUserVault');

  return useMutationWithFeedback<unknown, Error, Record<string, unknown>>({
    procedureName: 'UpdateUserVault',
    mutationFn: (params) => typedApi.UpdateUserVault(params as never),
    successMessage: messages?.success ?? 'Operation completed successfully',
    errorMessage: messages?.error ?? 'Operation failed',
    onSuccess: () => {
      invalidationKeys.forEach((key) => {
        void queryClient.invalidateQueries({ queryKey: [key] });
      });
    },
  });
};

// ============================================================================
// Bundled Mutation Hooks
// ============================================================================

export const useTeamMutations = () => ({
  createTeam: useCreateTeam(),
  updateTeamName: useUpdateTeamName(),
  updateTeamVault: useUpdateTeamVault(),
  deleteTeam: useDeleteTeam(),
});

export const useTeamMemberMutations = () => ({
  createTeamMembership: useCreateTeamMembership(),
  deleteUserFromTeam: useDeleteUserFromTeam(),
});

export const useMachineMutations = () => ({
  createMachine: useCreateMachine(),
  updateMachineName: useUpdateMachineName(),
  updateMachineAssignedBridge: useUpdateMachineAssignedBridge(),
  updateMachineVault: useUpdateMachineVault(),
  deleteMachine: useDeleteMachine(),
});

export const useRepositoryMutations = () => ({
  createRepository: useCreateRepository(),
  updateRepositoryName: useUpdateRepositoryName(),
  updateRepositoryTag: useUpdateRepositoryTag(),
  updateRepositoryVault: useUpdateRepositoryVault(),
  deleteRepository: useDeleteRepository(),
  promoteRepositoryToGrand: usePromoteRepositoryToGrand(),
});

export const useBridgeMutations = () => ({
  createBridge: useCreateBridge(),
  updateBridgeName: useUpdateBridgeName(),
  updateBridgeVault: useUpdateBridgeVault(),
  deleteBridge: useDeleteBridge(),
  resetBridgeAuthorization: useResetBridgeAuthorization(),
});

export const useStorageMutations = () => ({
  createStorage: useCreateStorage(),
  updateStorageName: useUpdateStorageName(),
  updateStorageVault: useUpdateStorageVault(),
  deleteStorage: useDeleteStorage(),
});

export const useRegionMutations = () => ({
  createRegion: useCreateRegion(),
  updateRegionName: useUpdateRegionName(),
  updateRegionVault: useUpdateRegionVault(),
  deleteRegion: useDeleteRegion(),
});

export const usePermissionMutations = () => ({
  createPermissionGroup: useCreatePermissionGroup(),
  deletePermissionGroup: useDeletePermissionGroup(),
  createPermissionInGroup: useCreatePermissionInGroup(),
  deletePermissionFromGroup: useDeletePermissionFromGroup(),
});

// ============================================================================
// Hook Aliases (for semantic naming)
// ============================================================================

export { useGetAuditLogs as useAuditLogs };
export { useGetEntityAuditTrace as useEntityAuditTrace };
export { useGetOrganizationDashboard as useOrganizationDashboard };
export { useGetQueueItemTrace as useQueueItemTrace };
export { useGetTeamQueueItems as useQueueItems };

