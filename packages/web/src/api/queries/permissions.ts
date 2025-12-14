import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import type { PermissionGroupWithParsedPermissions } from '@rediacc/shared/api';
import type {
  CreatePermissionGroupParams,
  CreatePermissionInGroupParams,
  DeletePermissionFromGroupParams,
  DeletePermissionGroupParams,
  Permission,
  UpdateUserAssignedPermissionsParams,
} from '@rediacc/shared/types';

// Get all permission groups
export const usePermissionGroups = () => {
  return useQuery<PermissionGroupWithParsedPermissions[]>({
    queryKey: ['permissionGroups'],
    queryFn: async () => {
      return api.permissions.listGroups();
    },
  });
};

// Get permission group details
export const usePermissionGroupDetails = (groupName: string) => {
  return useQuery({
    queryKey: ['permissionGroup', groupName],
    queryFn: async () => {
      const permissions = await api.permissions.getGroupDetails({ permissionGroupName: groupName });

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
    mutationFn: (params) => api.permissions.createGroup(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.groupCreated', { group: vars.permissionGroupName }),
    errorMessage: i18n.t('organization:access.errors.createGroupFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Delete permission group
export const useDeletePermissionGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeletePermissionGroupParams>({
    mutationFn: (params) => api.permissions.deleteGroup(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.groupDeleted', { group: vars.permissionGroupName }),
    errorMessage: i18n.t('organization:access.errors.deleteGroupFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Add permission to group
export const useAddPermissionToGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, CreatePermissionInGroupParams>({
    mutationFn: (params) => api.permissions.addPermission(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.permissionAdded', { permission: vars.permissionName }),
    errorMessage: i18n.t('organization:access.errors.addPermissionFailed'),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      queryClient.invalidateQueries({ queryKey: ['permissionGroup', vars.permissionGroupName] });
    },
  });
};

// Remove permission from group
export const useRemovePermissionFromGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeletePermissionFromGroupParams>({
    mutationFn: (params) => api.permissions.removePermission(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.permissionRemoved', { permission: vars.permissionName }),
    errorMessage: i18n.t('organization:access.errors.removePermissionFailed'),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      queryClient.invalidateQueries({ queryKey: ['permissionGroup', vars.permissionGroupName] });
    },
  });
};

// Assign user to permission group
export const useAssignUserToGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserAssignedPermissionsParams>({
    mutationFn: (params) => api.users.assignPermissions(params),
    successMessage: (_, vars) =>
      i18n.t('organization:access.success.userAssigned', { group: vars.permissionGroupName }),
    errorMessage: i18n.t('organization:access.errors.assignUserFailed'),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['permissionGroup', vars.permissionGroupName] });
    },
  });
};

export type {
  PermissionGroupWithParsedPermissions,
  PermissionGroupWithParsedPermissions as PermissionGroup,
  Permission,
};
