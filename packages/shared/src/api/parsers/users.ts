/**
 * User Parsers
 */

import { extractPrimaryOrSecondary, extractFirstByIndex } from './base';
import type { GetCompanyUsers_ResultSet1 } from '../../types';
import type { ApiResponse } from '../../types/api';

export function parseGetCompanyUsers(
  response: ApiResponse<GetCompanyUsers_ResultSet1>
): GetCompanyUsers_ResultSet1[] {
  return extractPrimaryOrSecondary(response).filter((user) => Boolean(user.userEmail));
}

export function parseCreateUser(
  response: ApiResponse<GetCompanyUsers_ResultSet1>
): GetCompanyUsers_ResultSet1 | null {
  return (
    extractFirstByIndex<GetCompanyUsers_ResultSet1>(response, 1) ??
    extractFirstByIndex<GetCompanyUsers_ResultSet1>(response, 0)
  );
}

export const parseUserList = parseGetCompanyUsers;
