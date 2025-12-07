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
      const response = await client.get<Team>('/GetCompanyTeams');
      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (team) => Boolean(team.teamName),
      });
    },

    create: async (params: WithOptionalVault<CreateTeamParams>): Promise<Team | null> => {
      const response = await client.post<Team>('/CreateTeam', {
        ...params,
        vaultContent: params.vaultContent ?? '{}',
      });
      return parseFirst(response, {
        extractor: responseExtractors.primaryOrSecondary,
      });
    },

    rename: (params: UpdateTeamNameParams) => client.post('/UpdateTeamName', params),

    delete: (params: DeleteTeamParams) => client.post('/DeleteTeam', params),

    updateVault: (params: UpdateTeamVaultParams) => client.post('/UpdateTeamVault', params),

    getMembers: async (params: GetTeamMembersParams): Promise<TeamMember[]> => {
      const response = await client.get<TeamMember>('/GetTeamMembers', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<TeamMember>(1),
      });
    },

    addMember: (params: CreateTeamMembershipParams) => client.post('/CreateTeamMembership', params),

    removeMember: (params: DeleteUserFromTeamParams) => client.post('/DeleteUserFromTeam', params),
  };
}
