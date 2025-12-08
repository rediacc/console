import { parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { Permission, GetCompanyPermissionGroups_ResultSet1 } from '../../types';
import type {
  CreatePermissionGroupParams,
  DeletePermissionGroupParams,
  CreatePermissionInGroupParams,
  DeletePermissionFromGroupParams,
  GetPermissionGroupDetailsParams,
} from '../../types';

export interface PermissionGroupWithParsedPermissions
  extends Omit<GetCompanyPermissionGroups_ResultSet1, 'permissions'> {
  permissions: string[];
}

export function createPermissionsService(client: ApiClient) {
  return {
    listGroups: async (): Promise<PermissionGroupWithParsedPermissions[]> => {
      const response = await client.get<GetCompanyPermissionGroups_ResultSet1>(
        '/GetCompanyPermissionGroups'
      );
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetCompanyPermissionGroups_ResultSet1>(1),
        map: (group): PermissionGroupWithParsedPermissions => {
          const rawPermissions = group.permissions as unknown;
          const permissions =
            typeof rawPermissions === 'string'
              ? rawPermissions
                  .split(',')
                  .map((permission) => permission.trim())
                  .filter(Boolean)
              : Array.isArray(rawPermissions)
                ? rawPermissions
                : [];

          return {
            ...group,
            permissions,
          };
        },
      });
    },

    getGroupDetails: async (params: GetPermissionGroupDetailsParams): Promise<Permission[]> => {
      const response = await client.get<Permission>('/GetPermissionGroupDetails', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<Permission>(1),
        filter: (permission) => Boolean(permission.permissionName),
      });
    },

    createGroup: (params: CreatePermissionGroupParams) =>
      client.post('/CreatePermissionGroup', params),

    deleteGroup: (params: DeletePermissionGroupParams) =>
      client.post('/DeletePermissionGroup', params),

    addPermission: (params: CreatePermissionInGroupParams) =>
      client.post('/CreatePermissionInGroup', params),

    removePermission: (params: DeletePermissionFromGroupParams) =>
      client.post('/DeletePermissionFromGroup', params),
  };
}
