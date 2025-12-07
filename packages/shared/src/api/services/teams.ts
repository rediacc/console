import { endpoints } from '../../endpoints';
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { Team, TeamMember } from '../../types';
import type {
  WithOptionalVault,
  CreateTeamParams,
  UpdateTeamNameParams,
  DeleteTeamParams,
  UpdateTeamVaultParams,
  GetTeamMembersParams,
  CreateTeamMembershipParams,
  DeleteUserFromTeamParams,
} from '../../types';

export function createTeamsService(client: ApiClient) {
  return {
    list: async (): Promise<Team[]> => {
      const response = await client.get<Team>(endpoints.company.getCompanyTeams);
      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (team) => Boolean(team.teamName),
      });
    },

    create: async (params: WithOptionalVault<CreateTeamParams>): Promise<Team | null> => {
      const response = await client.post<Team>(endpoints.teams.createTeam, {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      });
      return parseFirst(response, {
        extractor: responseExtractors.primaryOrSecondary,
      });
    },

    rename: (params: UpdateTeamNameParams) => client.post(endpoints.teams.updateTeamName, params),

    delete: (params: DeleteTeamParams) => client.post(endpoints.teams.deleteTeam, params),

    updateVault: (params: UpdateTeamVaultParams) =>
      client.post(endpoints.teams.updateTeamVault, params),

    getMembers: async (params: GetTeamMembersParams): Promise<TeamMember[]> => {
      const response = await client.get<TeamMember>(endpoints.teams.getTeamMembers, params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<TeamMember>(1),
      });
    },

    addMember: (params: CreateTeamMembershipParams) =>
      client.post(endpoints.teams.createTeamMembership, params),

    removeMember: (params: DeleteUserFromTeamParams) =>
      client.post(endpoints.teams.deleteUserFromTeam, params),
  };
}
