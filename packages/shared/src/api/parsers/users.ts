/**
 * User Parsers
 */

import { extractPrimaryOrSecondary, extractFirstByIndex } from './base';
import type { GetCompanyUsers_ResultSet1, CreateNewUser_ResultSet1 } from '../../types';
import type { ApiResponse } from '../../types/api';

export function parseGetCompanyUsers(
  response: ApiResponse<GetCompanyUsers_ResultSet1>
): GetCompanyUsers_ResultSet1[] {
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

export const parseUserList = parseGetCompanyUsers;
