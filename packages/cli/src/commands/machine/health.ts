import { Command } from 'commander';
import { parseGetTeamMachines } from '@rediacc/shared/api';
import { getMachineHealth, type MachineWithVaultStatus } from '@rediacc/shared/services/machine';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { contextService } from '../../services/context.js';
import { outputService } from '../../services/output.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

export function registerHealthCommand(machine: Command, program: Command): void {
  machine
    .command('health <name>')
    .description(t('commands.machine.health.description'))
    .option('-t, --team <name>', t('options.team'))
    .action(async (name: string, options: { team?: string }) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const apiResponse = await withSpinner(
          t('commands.machine.health.fetching'),
          () => typedApi.GetTeamMachines({ teamName: opts.team as string }),
          t('commands.machine.health.fetched')
        );

        const machines = parseGetTeamMachines(apiResponse as never);
        const machine = machines.find((m: MachineWithVaultStatus) => m.machineName === name);
        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const format = program.opts().output as OutputFormat;
        const health = getMachineHealth(machine);

        if (format === 'json') {
          outputService.print(health, format);
        } else {
          outputService.info(t('commands.machine.health.header', { name }));

          // Status line with color
          if (health.exitCode === 0) {
            outputService.success(t('commands.machine.health.statusHealthy'));
          } else if (health.exitCode === 1) {
            outputService.warn(t('commands.machine.health.statusWarning'));
          } else if (health.exitCode === 2) {
            outputService.error(t('commands.machine.health.statusError'));
          } else {
            outputService.error(t('commands.machine.health.statusCritical'));
          }

          // System section
          const sys = health.details.system;
          if (sys.uptime || sys.memoryPercent || sys.diskPercent || sys.datastorePercent) {
            outputService.info(t('commands.machine.health.systemSection'));
            if (sys.uptime) {
              outputService.info(t('commands.machine.health.systemUptime', { uptime: sys.uptime }));
            }
            if (sys.memoryPercent) {
              outputService.info(
                t('commands.machine.health.systemMemory', { percent: sys.memoryPercent })
              );
            }
            if (sys.diskPercent) {
              outputService.info(
                t('commands.machine.health.systemDisk', { percent: sys.diskPercent })
              );
            }
            if (sys.datastorePercent) {
              outputService.info(
                t('commands.machine.health.systemDatastore', { percent: sys.datastorePercent })
              );
            }
          }

          // Containers section
          const cont = health.details.containers;
          if (cont.total > 0) {
            outputService.info(t('commands.machine.health.containersSection'));
            outputService.info(
              t('commands.machine.health.containersSummary', {
                running: cont.running,
                total: cont.total,
                healthy: cont.healthy,
                unhealthy: cont.unhealthy,
              })
            );
          }

          // Services section
          const svc = health.details.services;
          if (svc.total > 0) {
            outputService.info(t('commands.machine.health.servicesSection'));
            outputService.info(
              t('commands.machine.health.servicesSummary', {
                active: svc.active,
                total: svc.total,
                failed: svc.failed,
              })
            );
          }

          // Storage section
          const stor = health.details.storage;
          if (stor.smartHealthy > 0 || stor.smartFailing > 0) {
            outputService.info(t('commands.machine.health.storageSection'));
            outputService.info(
              t('commands.machine.health.storageSmart', {
                healthy: stor.smartHealthy,
                failing: stor.smartFailing,
              })
            );
            if (stor.maxTemperature !== null) {
              outputService.info(
                t('commands.machine.health.storageTemp', { temp: stor.maxTemperature })
              );
            }
          }

          // Repositories section
          const repositoryStats = health.details.repositories;
          if (repositoryStats.total > 0) {
            outputService.info(t('commands.machine.health.repositoriesSection'));
            outputService.info(
              t('commands.machine.health.repositoriesSummary', {
                mounted: repositoryStats.mounted,
                total: repositoryStats.total,
                docker: repositoryStats.dockerRunning,
              })
            );
          }

          // Issues section
          if (health.issues.length > 0) {
            outputService.info(t('commands.machine.health.issuesSection'));
            for (const issue of health.issues) {
              outputService.warn(`  - ${issue}`);
            }
          }

          outputService.info(t('commands.machine.health.exitCode', { code: health.exitCode }));
        }

        // Exit with health-based code for CI
        if (health.exitCode !== 0) {
          process.exitCode = health.exitCode;
        }
      } catch (error) {
        handleError(error);
      }
    });
}
