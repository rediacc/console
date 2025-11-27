import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import { createResourceCommands } from '../utils/commandFactory.js'
import type { OutputFormat } from '../types/index.js'

export function registerTeamCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const team = createResourceCommands(program, {
    resourceName: 'team',
    resourceNamePlural: 'teams',
    nameField: 'teamName',
    parentOption: 'none',
    endpoints: {
      list: '/GetCompanyTeams',
      create: '/CreateTeam',
      rename: '/UpdateTeamName',
      delete: '/DeleteTeam'
    },
    vaultConfig: {
      endpoint: '/GetCompanyVaults',
      vaultType: 'Team'
    },
    vaultUpdateConfig: {
      endpoint: '/UpdateTeamVault',
      vaultFieldName: 'teamVault'
    }
  })

  // Add team member subcommand
  const member = team
    .command('member')
    .description('Team membership management')

  // team member list
  member
    .command('list <teamName>')
    .description('List team members')
    .action(async (teamName) => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching team members...',
          () => apiClient.get('/GetTeamMembers', { teamName }),
          'Members fetched'
        )

        const members = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        outputService.print(members, format)
      } catch (error) {
        handleError(error)
      }
    })

  // team member add
  member
    .command('add <teamName> <userEmail>')
    .description('Add a user to a team')
    .action(async (teamName, userEmail) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Adding ${userEmail} to team "${teamName}"...`,
          () => apiClient.post('/CreateTeamMembership', { teamName, newUserEmail: userEmail }),
          `User added to team "${teamName}"`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // team member remove
  member
    .command('remove <teamName> <userEmail>')
    .description('Remove a user from a team')
    .action(async (teamName, userEmail) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Removing ${userEmail} from team "${teamName}"...`,
          () => apiClient.post('/DeleteUserFromTeam', { teamName, removeUserEmail: userEmail }),
          `User removed from team "${teamName}"`
        )
      } catch (error) {
        handleError(error)
      }
    })
}
