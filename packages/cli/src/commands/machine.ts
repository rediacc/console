import { Command } from 'commander';
import { api } from '../services/api.js';
import {
  createResourceCommands,
  addStatusCommand,
  addAssignCommand,
} from '../utils/commandFactory.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { withSpinner } from '../utils/spinner.js';
import { handleError } from '../utils/errors.js';
import type { OutputFormat } from '../types/index.js';
import {
  parseVaultStatus,
  getDeploymentSummary,
  getMachineRepos,
  type MachineWithVaultStatus,
} from '@rediacc/shared/services/machine';

export function registerMachineCommands(program: Command): void {
  // Create standard CRUD commands using factory
  const machine = createResourceCommands(program, {
    resourceName: 'machine',
    resourceNamePlural: 'machines',
    nameField: 'machineName',
    parentOption: 'team',
    operations: {
      list: (params) => api.machines.list(params?.teamName as string | undefined),
      create: (payload) =>
        api.machines.create(
          payload.teamName as string,
          payload.machineName as string,
          payload.bridgeName as string,
          payload.vaultContent as string | undefined
        ),
      rename: (payload) =>
        api.machines.rename(
          payload.teamName as string,
          payload.currentMachineName as string,
          payload.newMachineName as string
        ),
      delete: (payload) =>
        api.machines.delete(payload.teamName as string, payload.machineName as string),
    },
    createOptions: [{ flags: '-b, --bridge <name>', description: 'Bridge name', required: true }],
    transformCreatePayload: (name, opts) => ({
      machineName: name,
      teamName: opts.team,
      bridgeName: opts.bridge,
    }),
    vaultConfig: {
      fetch: (params) => api.company.getAllVaults(params),
      vaultType: 'Machine',
    },
    vaultUpdateConfig: {
      update: (payload) =>
        api.machines.updateVault(
          payload.teamName as string,
          payload.machineName as string,
          payload.vaultContent as string,
          payload.vaultVersion as number
        ),
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
      api.machines.assignBridge(
        payload.teamName as string,
        payload.machineName as string,
        payload.newBridgeName as string
      ),
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
          outputService.info(`  Total Repos: ${summary.totalRepos}`);
          outputService.info(`  Mounted: ${summary.mountedCount}`);
          outputService.info(`  Docker Running: ${summary.dockerRunningCount}`);

          if (parsed.repos.length > 0) {
            outputService.info('\nDeployed Repositories:');
            parsed.repos.forEach((repo) => {
              outputService.info(
                `  - ${repo.name}${repo.size_human ? ` (${repo.size_human})` : ''}`
              );
              if (repo.mounted !== undefined) {
                outputService.info(`    Mounted: ${repo.mounted ? 'Yes' : 'No'}`);
              }
              if (repo.docker_running !== undefined) {
                outputService.info(`    Docker: ${repo.docker_running ? 'Running' : 'Stopped'}`);
              }
            });
          }
        }
      } catch (error) {
        handleError(error);
      }
    });

  // Add repos command to list deployed repos using shared parsing
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
        const repos = getMachineRepos(machine);
        const format = program.opts().output as OutputFormat;

        if (repos.length === 0) {
          outputService.info('No repositories deployed on this machine');
          return;
        }

        outputService.print(repos, format);
      } catch (error) {
        handleError(error);
      }
    });
}
