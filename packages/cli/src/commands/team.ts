import { Command } from 'commander';
import { authService } from '../services/auth.js';
import { api } from '../services/api.js';
import { outputService } from '../services/output.js';
import { withSpinner } from '../utils/spinner.js';
import { handleError } from '../utils/errors.js';
import { createResourceCommands } from '../utils/commandFactory.js';
import type { OutputFormat } from '../types/index.js';
export function registerTeamCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const team = createResourceCommands(program, {
    resourceName: 'team',
    resourceNamePlural: 'teams',
    nameField: 'teamName',
    parentOption: 'none',
    operations: {
      list: () => api.teams.list(),
      create: (payload) => api.teams.create(payload.teamName as string),
      rename: (payload) =>
        api.teams.rename(payload.currentTeamName as string, payload.newTeamName as string),
      delete: (payload) => api.teams.delete(payload.teamName as string),
    },
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Team',
    },
    vaultUpdateConfig: {
      update: (payload) =>
        api.teams.updateVault(
          payload.teamName as string,
          payload.vaultContent as string,
          payload.vaultVersion as number
        ),
      vaultFieldName: 'vaultContent',
    },
  });

  // Add team member subcommand
  const member = team.command('member').description('Team membership management');

  // team member list
  member
    .command('list <teamName>')
    .description('List team members')
    .action(async (teamName) => {
      try {
        await authService.requireAuth();

        const members = await withSpinner(
          'Fetching team members...',
          () => api.teams.getMembers(teamName),
          'Members fetched'
        );

        const format = program.opts().output as OutputFormat;

        outputService.print(members, format);
      } catch (error) {
        handleError(error);
      }
    });

  // team member add
  member
    .command('add <teamName> <userEmail>')
    .description('Add a user to a team')
    .action(async (teamName, userEmail) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          `Adding ${userEmail} to team "${teamName}"...`,
          () => api.teams.addMember(teamName, userEmail),
          `User added to team "${teamName}"`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // team member remove
  member
    .command('remove <teamName> <userEmail>')
    .description('Remove a user from a team')
    .action(async (teamName, userEmail) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          `Removing ${userEmail} from team "${teamName}"...`,
          () => api.teams.removeMember(teamName, userEmail),
          `User removed from team "${teamName}"`
        );
      } catch (error) {
        handleError(error);
      }
    });
}
