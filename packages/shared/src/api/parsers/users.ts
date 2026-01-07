/**
 * User Parsers
 */

import { extractPrimaryOrSecondary, extractFirstByIndex } from './base';
import type { GetOrganizationUsers_ResultSet1, CreateNewUser_ResultSet1 } from '../../types';
import type { ApiResponse } from '../../types/api';

export function parseGetOrganizationUsers(
  response: ApiResponse<GetOrganizationUsers_ResultSet1>
): GetOrganizationUsers_ResultSet1[] {
  return extractPrimaryOrSecondary(response).filter((user) => Boolean(user.userEmail));
}

export function parseCreateUser(
  response: ApiResponse<CreateNewUser_ResultSet1>
): CreateNewUser_ResultSet1 | null {
  return (
    extractFirstByIndex<CreateNewUser_ResultSet1>(response, 1) ??
    extractFirstByIndex<CreateNewUser_ResultSet1>(response, 0)
  );
}

export const parseUserList = parseGetOrganizationUsers;
