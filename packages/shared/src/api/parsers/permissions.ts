/**
 * Permission Parsers
 */

import { extractRowsByIndex, safeJsonParse } from './base';
import type {
  GetCompanyPermissionGroups_ResultSet1,
  GetPermissionGroupDetails_ResultSet1,
} from '../../types';
import type { ApiResponse } from '../../types/api';

export interface PermissionGroupWithPermissions extends GetCompanyPermissionGroups_ResultSet1 {
  parsedPermissions: Record<string, unknown>;
}

export function parseGetCompanyPermissionGroups(
  response: ApiResponse<GetCompanyPermissionGroups_ResultSet1>
): PermissionGroupWithPermissions[] {
  return extractRowsByIndex<GetCompanyPermissionGroups_ResultSet1>(response, 1).map((group) => ({
    ...group,
    parsedPermissions: group.permissions ? safeJsonParse(group.permissions, {}) : {},
  }));
}

export function parseGetPermissionGroupDetails(
  response: ApiResponse<GetPermissionGroupDetails_ResultSet1>
): GetPermissionGroupDetails_ResultSet1[] {
  return extractRowsByIndex<GetPermissionGroupDetails_ResultSet1>(response, 1);
}

export const parsePermissionGroups = parseGetCompanyPermissionGroups;
export const parsePermissionDetails = parseGetPermissionGroupDetails;
