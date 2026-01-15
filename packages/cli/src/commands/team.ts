import { Command } from 'commander';
import {
  parseGetOrganizationTeams,
  parseGetOrganizationVaults,
  parseGetTeamMembers,
} from '@rediacc/shared/api';
import type {
  CreateTeamParams,
  DeleteTeamParams,
  GetOrganizationVaults_ResultSet1,
  UpdateTeamNameParams,
  UpdateTeamVaultParams,
} from '@rediacc/shared/types';
import { t } from '../i18n/index.js';
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
        const response = await typedApi.GetOrganizationTeams({});
        return parseGetOrganizationTeams(response as never);
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
    transformCreatePayload: (name, _opts) => ({
      teamName: name,
    }),
    vaultConfig: {
      fetch: async () => {
        const response = await typedApi.GetOrganizationVaults({});
        const vaults = parseGetOrganizationVaults(response as never);
        return vaults as unknown as (GetOrganizationVaults_ResultSet1 & { vaultType?: string })[];
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
  const member = team.command('member').description(t('commands.team.member.description'));

  // team member list
  member
    .command('list <teamName>')
    .description(t('commands.team.member.list.description'))
    .action(async (teamName) => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.team.member.list.fetching'),
          () => typedApi.GetTeamMembers({ teamName }),
          t('commands.team.member.list.success')
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
    .description(t('commands.team.member.add.description'))
    .action(async (teamName, userEmail) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.team.member.add.adding', { email: userEmail, team: teamName }),
          () => typedApi.CreateTeamMembership({ teamName, newUserEmail: userEmail }),
          t('commands.team.member.add.success', { team: teamName })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // team member remove
  member
    .command('remove <teamName> <userEmail>')
    .description(t('commands.team.member.remove.description'))
    .action(async (teamName, userEmail) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.team.member.remove.removing', { email: userEmail, team: teamName }),
          () => typedApi.DeleteUserFromTeam({ teamName, removeUserEmail: userEmail }),
          t('commands.team.member.remove.success', { team: teamName })
        );
      } catch (error) {
        handleError(error);
      }
    });
}
