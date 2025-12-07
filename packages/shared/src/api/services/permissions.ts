import { endpoints } from '../../endpoints';
import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { Permission, PermissionGroup } from '../../types';
import type {
  CreatePermissionGroupParams,
  DeletePermissionGroupParams,
  CreatePermissionInGroupParams,
  DeletePermissionFromGroupParams,
  GetPermissionGroupDetailsParams,
} from '../../types';

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

    getGroupDetails: async (params: GetPermissionGroupDetailsParams): Promise<Permission[]> => {
      const response = await client.get<Permission>(
        endpoints.permissions.getPermissionGroupDetails,
        params
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Permission>(1),
        filter: (permission) => Boolean(permission.permissionName),
      });
    },

    createGroup: (params: CreatePermissionGroupParams) =>
      client.post(endpoints.permissions.createPermissionGroup, params),

    deleteGroup: (params: DeletePermissionGroupParams) =>
      client.post(endpoints.permissions.deletePermissionGroup, params),

    addPermission: (params: CreatePermissionInGroupParams) =>
      client.post(endpoints.permissions.createPermissionInGroup, params),

    removePermission: (params: DeletePermissionFromGroupParams) =>
      client.post(endpoints.permissions.deletePermissionFromGroup, params),
  };
}
