import { endpoints } from '../../endpoints'
import type { Team, TeamMember } from '../../types'
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse'
import type { ApiClient } from './types'

export function createTeamsService(client: ApiClient) {
  return {
    list: async (): Promise<Team[]> => {
      const response = await client.get<Team>(endpoints.company.getCompanyTeams)
      return parseResponse(response, {
        extractor: responseExtractors.primaryOrSecondary,
        filter: (team) => Boolean(team.teamName),
      })
    },

    create: async (teamName: string): Promise<Team | null> => {
      const response = await client.post<Team>(endpoints.teams.createTeam, { teamName })
      return parseFirst(response, {
        extractor: responseExtractors.primaryOrSecondary,
      })
    },

    rename: (currentName: string, newName: string) =>
      client.post(endpoints.teams.updateTeamName, {
        currentTeamName: currentName,
        newTeamName: newName,
      }),

    delete: (teamName: string) =>
      client.post(endpoints.teams.deleteTeam, { teamName }),

    updateVault: (teamName: string, vault: string, vaultVersion: number) =>
      client.post(endpoints.teams.updateTeamVault, {
        teamName,
        vaultContent: vault,
        vaultVersion,
      }),

    getMembers: async (teamName: string): Promise<TeamMember[]> => {
      const response = await client.get<TeamMember>(endpoints.teams.getTeamMembers, { teamName })
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<TeamMember>(1),
      })
    },

    addMember: (teamName: string, userEmail: string) =>
      client.post(endpoints.teams.createTeamMembership, {
        teamName,
        newUserEmail: userEmail,
      }),

    removeMember: (teamName: string, userEmail: string) =>
      client.post(endpoints.teams.deleteUserFromTeam, {
        teamName,
        removeUserEmail: userEmail,
      }),
  }
}
