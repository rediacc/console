import { endpoints } from '../../endpoints';
import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { Permission, PermissionGroup } from '../../types';

export function createPermissionsService(client: ApiClient) {
  return {
    listGroups: async (): Promise<PermissionGroup[]> => {
      const response = await client.get<PermissionGroup>(
        endpoints.company.getCompanyPermissionGroups
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<PermissionGroup>(1),
        map: (group) => {
          const rawPermissions = group.permissions as unknown;
          const permissions =
            typeof rawPermissions === 'string'
              ? rawPermissions
                  .split(',')
                  .map((permission) => permission.trim())
                  .filter(Boolean)
              : Array.isArray(rawPermissions)
                ? rawPermissions
                : (group.permissions ?? []);

          return {
            ...group,
            permissions,
          };
        },
      });
    },

    getGroupDetails: async (groupName: string): Promise<Permission[]> => {
      const response = await client.get<Permission>(
        endpoints.permissions.getPermissionGroupDetails,
        { permissionGroupName: groupName }
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Permission>(1),
        filter: (permission) => Boolean(permission.permissionName),
      });
    },

    createGroup: (groupName: string) =>
      client.post(endpoints.permissions.createPermissionGroup, { permissionGroupName: groupName }),

    deleteGroup: (groupName: string) =>
      client.post(endpoints.permissions.deletePermissionGroup, { permissionGroupName: groupName }),

    addPermission: (groupName: string, permissionName: string) =>
      client.post(endpoints.permissions.createPermissionInGroup, {
        permissionGroupName: groupName,
        permissionName,
      }),

    removePermission: (groupName: string, permissionName: string) =>
      client.post(endpoints.permissions.deletePermissionFromGroup, {
        permissionGroupName: groupName,
        permissionName,
      }),
  };
}
