/**
 * Company Parsers
 */

import { extractFirstByIndex, extractRowsByIndex } from './base';
import type {
  GetCompanyDashboardJson_ResultSet1,
  GetCompanyVault_ResultSet1,
  GetCompanyVaults_ResultSet1,
} from '../../types';
import type { ApiResponse } from '../../types/api';

export function parseGetCompanyDashboardJson(
  response: ApiResponse<GetCompanyDashboardJson_ResultSet1>
): GetCompanyDashboardJson_ResultSet1 | null {
  return (
    extractFirstByIndex<GetCompanyDashboardJson_ResultSet1>(response, 1) ??
    extractFirstByIndex<GetCompanyDashboardJson_ResultSet1>(response, 0)
  );
}

export function parseGetCompanyVault(
  response: ApiResponse<GetCompanyVault_ResultSet1>
): GetCompanyVault_ResultSet1 | null {
  return (
    extractFirstByIndex<GetCompanyVault_ResultSet1>(response, 1) ??
    extractFirstByIndex<GetCompanyVault_ResultSet1>(response, 0)
  );
}

export function parseGetCompanyVaults(
  response: ApiResponse<GetCompanyVaults_ResultSet1>
): GetCompanyVaults_ResultSet1[] {
  return extractRowsByIndex<GetCompanyVaults_ResultSet1>(response, 1);
}

export const parseDashboard = parseGetCompanyDashboardJson;
export const parseCompanyVault = parseGetCompanyVault;
