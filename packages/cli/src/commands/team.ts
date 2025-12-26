import { Command } from 'commander';
import {
  parseGetCompanyTeams,
  parseGetTeamMembers,
  parseGetCompanyVaults,
} from '@rediacc/shared/api';
import type {
  CreateTeamParams,
  DeleteTeamParams,
  UpdateTeamNameParams,
  UpdateTeamVaultParams,
  GetCompanyVaults_ResultSet1,
} from '@rediacc/shared/types';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { createResourceCommands } from '../utils/commandFactory.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';

export function registerTeamCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const team = createResourceCommands(program, {
    resourceName: 'team',
    resourceNamePlural: 'teams',
    nameField: 'teamName',
    parentOption: 'none',
    operations: {
      list: async () => {
        const response = await typedApi.GetCompanyTeams({});
        return parseGetCompanyTeams(response as never);
      },
      create: async (payload) => {
        await typedApi.CreateTeam(payload as unknown as CreateTeamParams);
      },
      rename: async (payload) => {
        await typedApi.UpdateTeamName(payload as unknown as UpdateTeamNameParams);
      },
      delete: async (payload) => {
        await typedApi.DeleteTeam(payload as unknown as DeleteTeamParams);
      },
    },
    vaultConfig: {
      fetch: async () => {
        const response = await typedApi.GetCompanyVaults({});
        const vaults = parseGetCompanyVaults(response as never);
        return vaults as unknown as (GetCompanyVaults_ResultSet1 & { vaultType?: string })[];
      },
      vaultType: 'Team',
    },
    vaultUpdateConfig: {
      update: async (payload) => {
        await typedApi.UpdateTeamVault(payload as unknown as UpdateTeamVaultParams);
      },
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

        const apiResponse = await withSpinner(
          'Fetching team members...',
          () => typedApi.GetTeamMembers({ teamName }),
          'Members fetched'
        );

        const members = parseGetTeamMembers(apiResponse as never);

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
          () => typedApi.CreateTeamMembership({ teamName, newUserEmail: userEmail }),
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
          () => typedApi.DeleteUserFromTeam({ teamName, removeUserEmail: userEmail }),
          `User removed from team "${teamName}"`
        );
      } catch (error) {
        handleError(error);
      }
    });
}
