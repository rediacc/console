/**
 * Permission Parsers
 */

import { extractRowsByIndex, safeJsonParse } from './base';
import type {
  GetOrganizationPermissionGroups_ResultSet1,
  GetPermissionGroupDetails_ResultSet1,
} from '../../types';
import type { ApiResponse } from '../../types/api';

export interface PermissionGroupWithPermissions extends GetOrganizationPermissionGroups_ResultSet1 {
  parsedPermissions: Record<string, unknown>;
}

export function parseGetOrganizationPermissionGroups(
  response: ApiResponse<GetOrganizationPermissionGroups_ResultSet1>
): PermissionGroupWithPermissions[] {
  return extractRowsByIndex<GetOrganizationPermissionGroups_ResultSet1>(response, 1).map(
    (group) => ({
      ...group,
      parsedPermissions: group.permissions ? safeJsonParse(group.permissions, {}) : {},
    })
  );
}

export function parseGetPermissionGroupDetails(
  response: ApiResponse<GetPermissionGroupDetails_ResultSet1>
): GetPermissionGroupDetails_ResultSet1[] {
  return extractRowsByIndex<GetPermissionGroupDetails_ResultSet1>(response, 1);
}

export const parsePermissionGroups = parseGetOrganizationPermissionGroups;
export const parsePermissionDetails = parseGetPermissionGroupDetails;
