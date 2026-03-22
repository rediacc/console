/**
 * Organization Parsers
 */

import type {
  GetOrganizationDashboard_ResultSet1,
  GetOrganizationDashboard_ResultSet2,
  GetOrganizationDashboard_ResultSet3,
  GetOrganizationDashboard_ResultSet4,
  GetOrganizationDashboard_ResultSet5,
  GetOrganizationDashboard_ResultSet6,
  GetOrganizationDashboard_ResultSet7,
  GetOrganizationDashboard_ResultSet8,
  GetOrganizationDashboard_ResultSet10,
  GetOrganizationDashboard_ResultSet11,
  GetOrganizationDashboard_ResultSet12,
  GetOrganizationDashboard_ResultSet13,
  GetOrganizationDashboard_ResultSet15,
  GetOrganizationVault_ResultSet1,
  GetOrganizationVaults_ResultSet1,
} from '../../types';
import type { ApiResponse } from '../../types/api';
import type { OrganizationDashboardData } from '../../types/derived';
import { extractFirstByIndex, extractRowsByIndex } from './base';

/**
 * Parse GetOrganizationDashboard response into OrganizationDashboardData
 * Extracts all result sets and combines them into a single object
 */
export function parseGetOrganizationDashboard(
  response: ApiResponse<unknown>
): OrganizationDashboardData {
  return {
    // ResultSet1: Organization info
    organizationInfo: extractFirstByIndex<GetOrganizationDashboard_ResultSet1>(response, 1),
    // ResultSet2: Active subscription
    activeSubscription: extractFirstByIndex<GetOrganizationDashboard_ResultSet2>(response, 2),
    // ResultSet3: All active subscriptions
    allActiveSubscriptions: extractRowsByIndex<GetOrganizationDashboard_ResultSet3>(response, 3),
    // ResultSet4: Resources
    resources: extractRowsByIndex<GetOrganizationDashboard_ResultSet4>(response, 4),
    // ResultSet5: Account health
    accountHealth: extractFirstByIndex<GetOrganizationDashboard_ResultSet5>(response, 5),
    // ResultSet6: Feature access
    featureAccess: extractFirstByIndex<GetOrganizationDashboard_ResultSet6>(response, 6),
    // ResultSet7: Plan limits
    planLimits: extractFirstByIndex<GetOrganizationDashboard_ResultSet7>(response, 7),
    // ResultSet8: Queue stats
    queueStats: extractFirstByIndex<GetOrganizationDashboard_ResultSet8>(response, 8),
    // ResultSet10: Team issues (ResultSet9 is user queue stats, not used here)
    teamIssues: extractRowsByIndex<GetOrganizationDashboard_ResultSet10>(response, 10),
    // ResultSet11: Machine issues
    machineIssues: extractRowsByIndex<GetOrganizationDashboard_ResultSet11>(response, 11),
    // ResultSet12: Active users
    activeUsers: extractRowsByIndex<GetOrganizationDashboard_ResultSet12>(response, 12),
    // ResultSet13: Ceph stats (Business/Enterprise only)
    cephStats: extractFirstByIndex<GetOrganizationDashboard_ResultSet13>(response, 13),
    // ResultSet15: Ceph team breakdown (Business/Enterprise only)
    cephTeamBreakdown: extractRowsByIndex<GetOrganizationDashboard_ResultSet15>(response, 15),
  };
}

/**
 * Parse organization info only from GetOrganizationDashboard response
 * Lighter weight extraction for MainLayout header
 */
export function parseOrganizationInfo(
  response: ApiResponse<unknown>
): Pick<OrganizationDashboardData, 'organizationInfo' | 'activeSubscription'> {
  return {
    organizationInfo: extractFirstByIndex<GetOrganizationDashboard_ResultSet1>(response, 1),
    activeSubscription: extractFirstByIndex<GetOrganizationDashboard_ResultSet2>(response, 2),
  };
}

export function parseGetOrganizationVault(
  response: ApiResponse<GetOrganizationVault_ResultSet1>
): GetOrganizationVault_ResultSet1 | null {
  return (
    extractFirstByIndex<GetOrganizationVault_ResultSet1>(response, 1) ??
    extractFirstByIndex<GetOrganizationVault_ResultSet1>(response, 0)
  );
}

export function parseGetOrganizationVaults(
  response: ApiResponse<GetOrganizationVaults_ResultSet1>
): GetOrganizationVaults_ResultSet1[] {
  return extractRowsByIndex<GetOrganizationVaults_ResultSet1>(response, 1);
}

export const parseDashboard = parseGetOrganizationDashboard;
export const parseOrganizationVault = parseGetOrganizationVault;
