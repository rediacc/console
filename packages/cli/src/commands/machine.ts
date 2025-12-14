import { Command } from 'commander';
import {
  getDeploymentSummary,
  getMachineRepositories,
  type MachineWithVaultStatus,
  parseVaultStatus,
} from '@rediacc/shared/services/machine';
import type {
  CreateMachineParams,
  DeleteMachineParams,
  UpdateMachineAssignedBridgeParams,
  UpdateMachineNameParams,
  UpdateMachineVaultParams,
} from '@rediacc/shared/types';
import { api } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import {
  addAssignCommand,
  addStatusCommand,
  createResourceCommands,
} from '../utils/commandFactory.js';
import { handleError } from '../utils/errors.js';
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
      list: (params) => api.machines.list(params?.teamName as string | undefined),
      create: (payload) => api.machines.create(payload as unknown as CreateMachineParams),
      rename: (payload) => api.machines.rename(payload as unknown as UpdateMachineNameParams),
      delete: (payload) => api.machines.delete(payload as unknown as DeleteMachineParams),
    },
    createOptions: [
      { flags: '-b, --bridge <name>', description: 'Bridge name', required: true },
      { flags: '--vault <json>', description: 'Machine vault data as JSON string' },
    ],
    transformCreatePayload: (name, opts) => {
      const payload: Record<string, unknown> = {
        machineName: name,
        teamName: opts.team,
        bridgeName: opts.bridge,
      };
      if (opts.vault) {
        payload.vaultContent = opts.vault;
      }
      return payload;
    },
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Machine',
    },
    vaultUpdateConfig: {
      update: (payload) => api.machines.updateVault(payload as unknown as UpdateMachineVaultParams),
      vaultFieldName: 'vaultContent',
    },
  });

  // Add status command
  addStatusCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    parentOption: 'team',
    fetch: (params) => api.machines.list(params.teamName as string | undefined),
  });

  // Add assign-bridge command
  addAssignCommand(machine, {
    resourceName: 'machine',
    nameField: 'machineName',
    targetName: 'bridge',
    targetField: 'newBridgeName',
    parentOption: 'team',
    perform: (payload) =>
      api.machines.assignBridge(payload as unknown as UpdateMachineAssignedBridgeParams),
  });

  // Add vault-status command using shared parsing
  machine
    .command('vault-status <name>')
    .description('Show parsed vault status for a machine')
    .option('-t, --team <name>', 'Team name')
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.');
          process.exit(1);
        }

        const machines = await withSpinner(
          'Fetching machine...',
          () => api.machines.list(opts.team as string),
          'Machine fetched'
        );

        const machine = machines.find((m: MachineWithVaultStatus) => m.machineName === name);
        if (!machine) {
          outputService.error(`Machine "${name}" not found`);
          process.exit(1);
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
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.');
          process.exit(1);
        }

        const machines = await withSpinner(
          'Fetching machine...',
          () => api.machines.list(opts.team as string),
          'Machine fetched'
        );

        const machine = machines.find((m: MachineWithVaultStatus) => m.machineName === name);
        if (!machine) {
          outputService.error(`Machine "${name}" not found`);
          process.exit(1);
        }

        // Use shared parsing service
        const repositories = getMachineRepositories(machine);
        const format = program.opts().output as OutputFormat;

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
