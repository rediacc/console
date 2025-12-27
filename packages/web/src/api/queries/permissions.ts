import { useQuery, useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import {
  parseGetCompanyPermissionGroups,
  parseGetPermissionGroupDetails,
} from '@rediacc/shared/api';
import type { PermissionGroupWithParsedPermissions } from '@rediacc/shared/api';
import type {
  CreatePermissionGroupParams,
  CreatePermissionInGroupParams,
  DeletePermissionFromGroupParams,
  DeletePermissionGroupParams,
  UpdateUserAssignedPermissionsParams,
} from '@rediacc/shared/types';

// Get all permission groups
export const usePermissionGroups = () => {
  return useQuery<PermissionGroupWithParsedPermissions[]>({
    queryKey: ['permissionGroups'],
    queryFn: async () => {
      const response = await typedApi.GetCompanyPermissionGroups({});
      return parseGetCompanyPermissionGroups(response as never);
    },
  });
};

// Get permission group details
export const usePermissionGroupDetails = (groupName: string) => {
  return useQuery({
    queryKey: ['permissionGroup', groupName],
    queryFn: async () => {
      const response = await typedApi.GetPermissionGroupDetails({
        permissionGroupName: groupName,
      });
      const permissions = parseGetPermissionGroupDetails(response as never);

      return {
        permissionGroupName: groupName,
        permissions: permissions.map((permission) => permission.permissionName).filter(Boolean),
      };
    },
    enabled: !!groupName,
  });
};

// Create permission group
export const useCreatePermissionGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, CreatePermissionGroupParams>({
    mutationFn: (params) => typedApi.CreatePermissionGroup(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.groupCreated', { group: vars.permissionGroupName }),
    errorMessage: i18n.t('organization:access.errors.createGroupFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      void queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Delete permission group
export const useDeletePermissionGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeletePermissionGroupParams>({
    mutationFn: (params) => typedApi.DeletePermissionGroup(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.groupDeleted', { group: vars.permissionGroupName }),
    errorMessage: i18n.t('organization:access.errors.deleteGroupFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      void queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Add permission to group
export const useAddPermissionToGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, CreatePermissionInGroupParams>({
    mutationFn: (params) => typedApi.CreatePermissionInGroup(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.permissionAdded', { permission: vars.permissionName }),
    errorMessage: i18n.t('organization:access.errors.addPermissionFailed'),
    onSuccess: (_, vars) => {
      void queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      void queryClient.invalidateQueries({
        queryKey: ['permissionGroup', vars.permissionGroupName],
      });
    },
  });
};

// Remove permission from group
export const useRemovePermissionFromGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeletePermissionFromGroupParams>({
    mutationFn: (params) => typedApi.DeletePermissionFromGroup(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.permissionRemoved', { permission: vars.permissionName }),
    errorMessage: i18n.t('organization:access.errors.removePermissionFailed'),
    onSuccess: (_, vars) => {
      void queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      void queryClient.invalidateQueries({
        queryKey: ['permissionGroup', vars.permissionGroupName],
      });
    },
  });
};

// Assign user to permission group
export const useAssignUserToGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserAssignedPermissionsParams>({
    mutationFn: (params) => typedApi.UpdateUserAssignedPermissions(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.userAssigned', { group: vars.permissionGroupName }),
    errorMessage: i18n.t('organization:access.errors.assignUserFailed'),
    onSuccess: (_, vars) => {
      void queryClient.invalidateQueries({ queryKey: ['users'] });
      void queryClient.invalidateQueries({
        queryKey: ['permissionGroup', vars.permissionGroupName],
      });
    },
  });
};

export type { Permission } from '@rediacc/shared/types';
export type {
  PermissionGroupWithParsedPermissions,
  PermissionGroupWithParsedPermissions as PermissionGroup,
} from '@rediacc/shared/api';
