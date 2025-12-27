/**
 * Team Parsers
 */

import { extractPrimaryOrSecondary, extractRowsByIndex } from './base';
import type { GetCompanyTeams_ResultSet1, GetTeamMembers_ResultSet1 } from '../../types';
import type { ApiResponse } from '../../types/api';

export function parseGetCompanyTeams(
  response: ApiResponse<GetCompanyTeams_ResultSet1>
): GetCompanyTeams_ResultSet1[] {
  return extractPrimaryOrSecondary(response).filter((team) => Boolean(team.teamName));
}

export function parseGetTeamMembers(
  response: ApiResponse<GetTeamMembers_ResultSet1>
): GetTeamMembers_ResultSet1[] {
  return extractRowsByIndex<GetTeamMembers_ResultSet1>(response, 1);
}

export const parseTeamList = parseGetCompanyTeams;
export const parseTeamMembers = parseGetTeamMembers;
