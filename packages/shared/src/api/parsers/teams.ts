/**
 * Team Parsers
 */

import type { GetOrganizationTeams_ResultSet1, GetTeamMembers_ResultSet1 } from '../../types';
import type { ApiResponse } from '../../types/api';
import { extractPrimaryOrSecondary, extractRowsByIndex } from './base';

export function parseGetOrganizationTeams(
  response: ApiResponse<GetOrganizationTeams_ResultSet1>
): GetOrganizationTeams_ResultSet1[] {
  return extractPrimaryOrSecondary(response).filter((team) => Boolean(team.teamName));
}

export function parseGetTeamMembers(
  response: ApiResponse<GetTeamMembers_ResultSet1>
): GetTeamMembers_ResultSet1[] {
  return extractRowsByIndex<GetTeamMembers_ResultSet1>(response, 1);
}

export const parseTeamList = parseGetOrganizationTeams;
export const parseTeamMembers = parseGetTeamMembers;
