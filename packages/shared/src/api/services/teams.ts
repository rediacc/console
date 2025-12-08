import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type {
  CreateTeamMembershipParams,
  CreateTeamParams,
  DeleteTeamParams,
  DeleteUserFromTeamParams,
  GetCompanyTeams_ResultSet1,
  GetTeamMembers_ResultSet1,
  GetTeamMembersParams,
  UpdateTeamNameParams,
  UpdateTeamVaultParams,
  WithOptionalVault,
} from '../../types';

export function createTeamsService(client: ApiClient) {
  return {
    list: async (): Promise<GetCompanyTeams_ResultSet1[]> => {
      const response = await client.get<GetCompanyTeams_ResultSet1>('/GetCompanyTeams');
      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (team) => Boolean(team.teamName),
      });
    },

    create: async (
      params: WithOptionalVault<CreateTeamParams>
    ): Promise<GetCompanyTeams_ResultSet1 | null> => {
      const response = await client.post<GetCompanyTeams_ResultSet1>('/CreateTeam', {
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

    getMembers: async (params: GetTeamMembersParams): Promise<GetTeamMembers_ResultSet1[]> => {
      const response = await client.get<GetTeamMembers_ResultSet1>('/GetTeamMembers', params);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetTeamMembers_ResultSet1>(1),
      });
    },

    addMember: (params: CreateTeamMembershipParams) => client.post('/CreateTeamMembership', params),

    removeMember: (params: DeleteUserFromTeamParams) => client.post('/DeleteUserFromTeam', params),
  };
}
