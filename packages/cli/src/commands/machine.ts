import { Command } from 'commander';
import {
  parseGetTeamMachines,
  parseCreateMachine,
  parseGetCompanyVaults,
} from '@rediacc/shared/api';
import {
  getDeploymentSummary,
  getMachineRepositories,
  type MachineWithVaultStatus,
  parseVaultStatus,
} from '@rediacc/shared/services/machine';
import type {
  GetCompanyVaults_ResultSet1,
  CreateMachineParams,
  DeleteMachineParams,
  UpdateMachineAssignedBridgeParams,
  UpdateMachineNameParams,
  UpdateMachineVaultParams,
} from '@rediacc/shared/types';
import { searchInFields } from '@rediacc/shared/utils';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import {
  addAssignCommand,
  addStatusCommand,
  createResourceCommands,
} from '../utils/commandFactory.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';

export function registerMachineCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const machine = createResourceCommands(program, {
    resourceName: 'machine',
    resourceNamePlural: 'machines',
    nameField: 'machineName',
    parentOption: 'team',
    operations: {
      list: async (params) => {
        const response = await typedApi.GetTeamMachines({
          teamName: params?.teamName as string | undefined,
        });
        return parseGetTeamMachines(response as never);
      },
      create: async (payload) => {
        const response = await typedApi.CreateMachine(payload as unknown as CreateMachineParams);
        return parseCreateMachine(response as never);
      },
      rename: (payload) =>
        typedApi.UpdateMachineName(payload as unknown as UpdateMachineNameParams),
      delete: (payload) => typedApi.DeleteMachine(payload as unknown as DeleteMachineParams),
    },
    createOptions: [
      { flags: '-b, --bridge <name>', description: 'Bridge name', required: true },
      { flags: '--vault <json>', description: 'Machine vault data as JSON string' },
    ],
    transformCreatePayload: (name, opts) => ({
      machineName: name,
      teamName: opts.team,
      bridgeName: opts.bridge,
      vaultContent: opts.vault,
    }),
    vaultConfig: {
      fetch: async () => {
        const response = await typedApi.GetCompanyVaults({});
        const vaults = parseGetCompanyVaults(response as never);
        return vaults as unknown as (GetCompanyVaults_ResultSet1 & { vaultType?: string })[];
      },
      vaultType: 'Machine',
    },
    vaultUpdateConfig: {
      update: (payload) =>
        typedApi.UpdateMachineVault(payload as unknown as UpdateMachineVaultParams),
      vaultFieldName: 'vaultContent',
    },
  });

  // Add status command
  addStatusCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    parentOption: 'team',
    fetch: async (params) => {
      const response = await typedApi.GetTeamMachines({
        teamName: params.teamName as string | undefined,
      });
      return parseGetTeamMachines(response as never);
    },
  });

  // Add assign-bridge command
  addAssignCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    targetName: 'bridge',
    targetField: 'newBridgeName',
    parentOption: 'team',
    perform: (payload) =>
      typedApi.UpdateMachineAssignedBridge(payload as unknown as UpdateMachineAssignedBridgeParams),
  });

  // Add vault-status command using shared parsing
  machine
    .command('vault-status <name>')
    .description('Show parsed vault status for a machine')
    .option('-t, --team <name>', 'Team name')
    .action(async (name: string, options: { team?: string }) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        const apiResponse = await withSpinner(
          'Fetching machine...',
          () => typedApi.GetTeamMachines({ teamName: opts.team as string }),
          'Machine fetched'
        );

        const machines = parseGetTeamMachines(apiResponse as never);
        const machine = machines.find((m: MachineWithVaultStatus) => m.machineName === name);
        if (!machine) {
          throw new ValidationError(`Machine "${name}" not found`);
        }

        const format = program.opts().output as OutputFormat;

        // Use shared parsing service
        const parsed = parseVaultStatus(machine.vaultStatus);
        const summary = getDeploymentSummary(machine);

        if (format === 'json') {
          outputService.print({ parsed, summary }, format);
        } else {
          outputService.info(`\nVault Status for ${name}:`);
          outputService.info(`  Status: ${summary.status}`);
          outputService.info(`  Total Repositories: ${summary.totalRepositories}`);
          outputService.info(`  Mounted: ${summary.mountedCount}`);
          outputService.info(`  Docker Running: ${summary.dockerRunningCount}`);

          if (parsed.repositories.length > 0) {
            outputService.info('\nDeployed Repositories:');
            parsed.repositories.forEach((repository) => {
              outputService.info(
                `  - ${repository.name}${repository.size_human ? ` (${repository.size_human})` : ''}`
              );
              if (repository.mounted !== undefined) {
                outputService.info(`    Mounted: ${repository.mounted ? 'Yes' : 'No'}`);
              }
              if (repository.docker_running !== undefined) {
                outputService.info(
                  `    Docker: ${repository.docker_running ? 'Running' : 'Stopped'}`
                );
              }
            });
          }
        }
      } catch (error) {
        handleError(error);
      }
    });

  // Add repositories command to list deployed repositories using shared parsing
  machine
    .command('repos <name>')
    .description('List deployed repositories on a machine')
    .option('-t, --team <name>', 'Team name')
    .option('--search <text>', 'Filter repositories by name')
    .action(async (name: string, options: { team?: string; search?: string }) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        const apiResponse = await withSpinner(
          'Fetching machine...',
          () => typedApi.GetTeamMachines({ teamName: opts.team as string }),
          'Machine fetched'
        );

        const machines = parseGetTeamMachines(apiResponse as never);
        const machine = machines.find((m: MachineWithVaultStatus) => m.machineName === name);
        if (!machine) {
          throw new ValidationError(`Machine "${name}" not found`);
        }

        // Use shared parsing service
        let repositories = getMachineRepositories(machine);
        const format = program.opts().output as OutputFormat;

        // Filter by search term
        if (options.search) {
          const searchTerm = options.search;
          repositories = repositories.filter((repo) =>
            searchInFields(repo, searchTerm, ['name', 'repositoryGuid'])
          );
        }

        if (repositories.length === 0) {
          outputService.info('No repositories deployed on this machine');
          return;
        }

        outputService.print(repositories, format);
      } catch (error) {
        handleError(error);
      }
    });
}
