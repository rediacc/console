import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { createMutation } from '@/hooks/api/mutationFactory';
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
export const useCreatePermissionGroup = createMutation<CreatePermissionGroupParams>({
  request: (params) => api.permissions.createGroup(params),
  invalidateKeys: ['permissionGroups', 'dropdown-data'],
  successMessage: (vars) =>
    i18n.t('organization:access.success.groupCreated', { group: vars.permissionGroupName }),
  errorMessage: i18n.t('organization:access.errors.createGroupFailed'),
  operationName: 'permissions.createGroup',
});

// Delete permission group
export const useDeletePermissionGroup = createMutation<DeletePermissionGroupParams>({
  request: (params) => api.permissions.deleteGroup(params),
  invalidateKeys: ['permissionGroups', 'dropdown-data'],
  successMessage: (vars) =>
    i18n.t('organization:access.success.groupDeleted', { group: vars.permissionGroupName }),
  errorMessage: i18n.t('organization:access.errors.deleteGroupFailed'),
  operationName: 'permissions.deleteGroup',
});

// Add permission to group
export const useAddPermissionToGroup = createMutation<CreatePermissionInGroupParams>({
  request: (params) => api.permissions.addPermission(params),
  invalidateKeys: ['permissionGroups'],
  additionalInvalidateKeys: (vars) => [['permissionGroup', vars.permissionGroupName]],
  successMessage: (vars) =>
    i18n.t('organization:access.success.permissionAdded', { permission: vars.permissionName }),
  errorMessage: i18n.t('organization:access.errors.addPermissionFailed'),
  operationName: 'permissions.addPermission',
});

// Remove permission from group
export const useRemovePermissionFromGroup = createMutation<DeletePermissionFromGroupParams>({
  request: (params) => api.permissions.removePermission(params),
  invalidateKeys: ['permissionGroups'],
  additionalInvalidateKeys: (vars) => [['permissionGroup', vars.permissionGroupName]],
  successMessage: (vars) =>
    i18n.t('organization:access.success.permissionRemoved', { permission: vars.permissionName }),
  errorMessage: i18n.t('organization:access.errors.removePermissionFailed'),
  operationName: 'permissions.removePermission',
});

// Assign user to permission group
export const useAssignUserToGroup = createMutation<UpdateUserAssignedPermissionsParams>({
  request: (params) => api.users.assignPermissions(params),
  invalidateKeys: ['users'],
  additionalInvalidateKeys: (vars) => [['permissionGroup', vars.permissionGroupName]],
  successMessage: (vars) =>
    i18n.t('organization:access.success.userAssigned', { group: vars.permissionGroupName }),
  errorMessage: i18n.t('organization:access.errors.assignUserFailed'),
  operationName: 'permissions.assignUser',
});

export type {
  PermissionGroupWithParsedPermissions,
  PermissionGroupWithParsedPermissions as PermissionGroup,
  Permission,
};
