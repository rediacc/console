import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { contextService } from '../services/context.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'

export function registerTeamCommands(program: Command): void {
  const team = program
    .command('team')
    .description('Team management commands')

  // team list
  team
    .command('list')
    .description('List all teams')
    .action(async () => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching teams...',
          () => apiClient.get('/GetCompanyTeams', {}),
          'Teams fetched'
        )

        const teams = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        outputService.print(teams, format)
      } catch (error) {
        handleError(error)
      }
    })

  // team create
  team
    .command('create <name>')
    .description('Create a new team')
    .action(async (name) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Creating team "${name}"...`,
          () => apiClient.post('/CreateTeam', { teamName: name }),
          `Team "${name}" created`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // team rename
  team
    .command('rename <oldName> <newName>')
    .description('Rename a team')
    .action(async (oldName, newName) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Renaming team "${oldName}" to "${newName}"...`,
          () => apiClient.post('/UpdateTeamName', {
            currentTeamName: oldName,
            newTeamName: newName,
          }),
          `Team renamed to "${newName}"`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // team delete
  team
    .command('delete <name>')
    .description('Delete a team')
    .option('-f, --force', 'Skip confirmation')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js')
          const confirm = await askConfirm(`Delete team "${name}"? This cannot be undone.`)
          if (!confirm) {
            outputService.info('Cancelled')
            return
          }
        }

        await withSpinner(
          `Deleting team "${name}"...`,
          () => apiClient.post('/DeleteTeam', { teamName: name }),
          `Team "${name}" deleted`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // team vault subcommand
  const vault = team
    .command('vault')
    .description('Team vault management')

  // team vault get
  vault
    .command('get <teamName>')
    .description('Get team vault data')
    .action(async (teamName) => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching team vault...',
          () => apiClient.get('/GetCompanyVaults', { teamName }),
          'Vault fetched'
        )

        const vaults = response.resultSets?.[0]?.data || []
        const teamVault = vaults.find((v: any) => v.vaultType === 'Team')
        const format = program.opts().output as OutputFormat

        if (teamVault) {
          outputService.print(teamVault, format)
        } else {
          outputService.info('No team vault found')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // team member subcommand
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
