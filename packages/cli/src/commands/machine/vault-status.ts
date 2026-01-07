import { Command } from 'commander';
import { parseGetTeamMachines } from '@rediacc/shared/api';
import {
  getDeploymentSummary,
  getMachineSystemInfo,
  parseListResult,
  type MachineWithVaultStatus,
  parseVaultStatus,
} from '@rediacc/shared/services/machine';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { contextService } from '../../services/context.js';
import { outputService } from '../../services/output.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

export function registerVaultStatusCommand(machine: Command, program: Command): void {
  machine
    .command('vault-status <name>')
    .description(t('commands.machine.vaultStatus.description'))
    .option('-t, --team <name>', t('options.team'))
    .action(async (name: string, options: { team?: string }) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const apiResponse = await withSpinner(
          t('commands.machine.vaultStatus.fetching'),
          () => typedApi.GetTeamMachines({ teamName: opts.team as string }),
          t('commands.machine.vaultStatus.fetched')
        );

        const machines = parseGetTeamMachines(apiResponse as never);
        const machine = machines.find((m: MachineWithVaultStatus) => m.machineName === name);
        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const format = program.opts().output as OutputFormat;

        // Use shared parsing service
        const parsed = parseVaultStatus(machine.vaultStatus);
        const summary = getDeploymentSummary(machine);
        const systemInfo = getMachineSystemInfo(machine);
        const listResult = parseListResult(machine.vaultStatus);

        if (format === 'json') {
          outputService.print({ parsed, summary, systemInfo, listResult }, format);
        } else {
          outputService.info(t('commands.machine.vaultStatus.header', { name }));
          outputService.info(t('commands.machine.vaultStatus.status', { status: summary.status }));

          // Show system info if available
          if (systemInfo) {
            outputService.info(t('commands.machine.vaultStatus.systemSection'));
            if (systemInfo.hostname) {
              outputService.info(
                t('commands.machine.vaultStatus.systemHostname', { hostname: systemInfo.hostname })
              );
            }
            if (systemInfo.uptime) {
              outputService.info(
                t('commands.machine.vaultStatus.systemUptime', { uptime: systemInfo.uptime })
              );
            }
            outputService.info(
              t('commands.machine.vaultStatus.systemMemory', {
                used: systemInfo.memory.used,
                total: systemInfo.memory.total,
                percent: systemInfo.memory.use_percent ?? 'N/A',
              })
            );
            outputService.info(
              t('commands.machine.vaultStatus.systemDisk', {
                used: systemInfo.disk.used,
                total: systemInfo.disk.total,
                percent: systemInfo.disk.use_percent ?? 'N/A',
              })
            );
            outputService.info(
              t('commands.machine.vaultStatus.systemDatastore', {
                used: systemInfo.datastore.used,
                total: systemInfo.datastore.total,
                percent: systemInfo.datastore.use_percent ?? 'N/A',
              })
            );
          }

          outputService.info(
            t('commands.machine.vaultStatus.totalRepos', { count: summary.totalRepositories })
          );
          outputService.info(
            t('commands.machine.vaultStatus.mounted', { count: summary.mountedCount })
          );
          outputService.info(
            t('commands.machine.vaultStatus.dockerRunning', { count: summary.dockerRunningCount })
          );

          if (parsed.repositories.length > 0) {
            outputService.info(t('commands.machine.vaultStatus.deployedRepos'));
            parsed.repositories.forEach((repository) => {
              outputService.info(
                `  - ${repository.name}${repository.size_human ? ` (${repository.size_human})` : ''}`
              );
              if (repository.mounted !== undefined) {
                outputService.info(
                  t('commands.machine.vaultStatus.repoMounted', {
                    mounted: repository.mounted ? t('common.yes') : t('common.no'),
                  })
                );
              }
              if (repository.docker_running !== undefined) {
                outputService.info(
                  t('commands.machine.vaultStatus.repoDocker', {
                    status: repository.docker_running ? t('common.running') : t('common.stopped'),
                  })
                );
              }
            });
          }
        }
      } catch (error) {
        handleError(error);
      }
    });
}
