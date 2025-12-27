/**
 * Company Parsers
 */

import { extractFirstByIndex, extractRowsByIndex } from './base';
import type {
  GetCompanyDashboard_ResultSet1,
  GetCompanyDashboard_ResultSet2,
  GetCompanyDashboard_ResultSet3,
  GetCompanyDashboard_ResultSet4,
  GetCompanyDashboard_ResultSet5,
  GetCompanyDashboard_ResultSet6,
  GetCompanyDashboard_ResultSet7,
  GetCompanyDashboard_ResultSet8,
  GetCompanyDashboard_ResultSet10,
  GetCompanyDashboard_ResultSet11,
  GetCompanyDashboard_ResultSet12,
  GetCompanyDashboard_ResultSet13,
  GetCompanyDashboard_ResultSet15,
  GetCompanyVault_ResultSet1,
  GetCompanyVaults_ResultSet1,
} from '../../types';
import type { CompanyDashboardData } from '../../types/derived';
import type { ApiResponse } from '../../types/api';

/**
 * Parse GetCompanyDashboard response into CompanyDashboardData
 * Extracts all result sets and combines them into a single object
 */
export function parseGetCompanyDashboard(response: ApiResponse<unknown>): CompanyDashboardData {
  return {
    // ResultSet1: Company info
    companyInfo: extractFirstByIndex<GetCompanyDashboard_ResultSet1>(response, 1),
    // ResultSet2: Active subscription
    activeSubscription: extractFirstByIndex<GetCompanyDashboard_ResultSet2>(response, 2),
    // ResultSet3: All active subscriptions
    allActiveSubscriptions: extractRowsByIndex<GetCompanyDashboard_ResultSet3>(response, 3),
    // ResultSet4: Resources
    resources: extractRowsByIndex<GetCompanyDashboard_ResultSet4>(response, 4),
    // ResultSet5: Account health
    accountHealth: extractFirstByIndex<GetCompanyDashboard_ResultSet5>(response, 5),
    // ResultSet6: Feature access
    featureAccess: extractFirstByIndex<GetCompanyDashboard_ResultSet6>(response, 6),
    // ResultSet7: Plan limits
    planLimits: extractFirstByIndex<GetCompanyDashboard_ResultSet7>(response, 7),
    // ResultSet8: Queue stats
    queueStats: extractFirstByIndex<GetCompanyDashboard_ResultSet8>(response, 8),
    // ResultSet10: Team issues (ResultSet9 is user queue stats, not used here)
    teamIssues: extractRowsByIndex<GetCompanyDashboard_ResultSet10>(response, 10),
    // ResultSet11: Machine issues
    machineIssues: extractRowsByIndex<GetCompanyDashboard_ResultSet11>(response, 11),
    // ResultSet12: Active users
    activeUsers: extractRowsByIndex<GetCompanyDashboard_ResultSet12>(response, 12),
    // ResultSet13: Ceph stats (Business/Enterprise only)
    cephStats: extractFirstByIndex<GetCompanyDashboard_ResultSet13>(response, 13),
    // ResultSet15: Ceph team breakdown (Business/Enterprise only)
    cephTeamBreakdown: extractRowsByIndex<GetCompanyDashboard_ResultSet15>(response, 15),
  };
}

/**
 * Parse company info only from GetCompanyDashboard response
 * Lighter weight extraction for MainLayout header
 */
export function parseCompanyInfo(
  response: ApiResponse<unknown>
): Pick<CompanyDashboardData, 'companyInfo' | 'activeSubscription'> {
  return {
    companyInfo: extractFirstByIndex<GetCompanyDashboard_ResultSet1>(response, 1),
    activeSubscription: extractFirstByIndex<GetCompanyDashboard_ResultSet2>(response, 2),
  };
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

export const parseDashboard = parseGetCompanyDashboard;
export const parseCompanyVault = parseGetCompanyVault;
