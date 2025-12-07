import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import i18n from '@/i18n/config';
import { showMessage } from '@/utils/messages';
import { createErrorHandler } from '@/utils/mutationUtils';
import type {
  Permission,
  PermissionGroup,
  CreatePermissionGroupParams,
  DeletePermissionGroupParams,
  CreatePermissionInGroupParams,
  DeletePermissionFromGroupParams,
  UpdateUserAssignedPermissionsParams,
} from '@rediacc/shared/types';

// Get all permission groups
export const usePermissionGroups = () => {
  return useQuery<PermissionGroup[]>({
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

  return useMutation({
    mutationFn: async (params: CreatePermissionGroupParams) => {
      return api.permissions.createGroup(params);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
      showMessage(
        'success',
        i18n.t('organization:access.success.groupCreated', { group: variables.permissionGroupName })
      );
    },
    onError: createErrorHandler(i18n.t('organization:access.errors.createGroupFailed')),
  });
};

// Delete permission group
export const useDeletePermissionGroup = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: DeletePermissionGroupParams) => {
      return api.permissions.deleteGroup(params);
    },
    onSuccess: (_, params) => {
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
      showMessage(
        'success',
        i18n.t('organization:access.success.groupDeleted', { group: params.permissionGroupName })
      );
    },
    onError: createErrorHandler(i18n.t('organization:access.errors.deleteGroupFailed')),
  });
};

// Add permission to group
export const useAddPermissionToGroup = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: CreatePermissionInGroupParams) => {
      return api.permissions.addPermission(params);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['permissionGroup', variables.permissionGroupName],
      });
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] }); // Update permission counts
      showMessage(
        'success',
        i18n.t('organization:access.success.permissionAdded', {
          permission: variables.permissionName,
        })
      );
    },
    onError: createErrorHandler(i18n.t('organization:access.errors.addPermissionFailed')),
  });
};

// Remove permission from group
export const useRemovePermissionFromGroup = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: DeletePermissionFromGroupParams) => {
      return api.permissions.removePermission(params);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['permissionGroup', variables.permissionGroupName],
      });
      queryClient.invalidateQueries({ queryKey: ['permissionGroups'] }); // Update permission counts
      showMessage(
        'success',
        i18n.t('organization:access.success.permissionRemoved', {
          permission: variables.permissionName,
        })
      );
    },
    onError: createErrorHandler(i18n.t('organization:access.errors.removePermissionFailed')),
  });
};

// Assign user to permission group
export const useAssignUserToGroup = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: UpdateUserAssignedPermissionsParams) => {
      return api.users.assignPermissions(params);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({
        queryKey: ['permissionGroup', variables.permissionGroupName],
      });
      showMessage(
        'success',
        i18n.t('organization:access.success.userAssigned', { group: variables.permissionGroupName })
      );
    },
    onError: createErrorHandler(i18n.t('organization:access.errors.assignUserFailed')),
  });
};

export type { PermissionGroup, Permission };
