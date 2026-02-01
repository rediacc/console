import { Command } from 'commander';
import { getMachineHealth, type MachineHealthResult } from '@rediacc/shared/services/machine';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { authService } from '../../services/auth.js';
import { contextService } from '../../services/context.js';
import { outputService } from '../../services/output.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

const exitCodeStatusHandlers: Record<number, () => void> = {
  0: () => outputService.success(t('commands.machine.health.statusHealthy')),
  1: () => outputService.warn(t('commands.machine.health.statusWarning')),
  2: () => outputService.error(t('commands.machine.health.statusError')),
};

function displayStatusByExitCode(exitCode: number): void {
  const handler = exitCodeStatusHandlers[exitCode] as (() => void) | undefined;
  if (handler === undefined) {
    outputService.error(t('commands.machine.health.statusCritical'));
  } else {
    handler();
  }
}

function displaySystemSection(sys: MachineHealthResult['details']['system']): void {
  const hasData = sys.uptime ?? sys.memoryPercent ?? sys.diskPercent ?? sys.datastorePercent;
  if (!hasData) return;

  outputService.info(t('commands.machine.health.systemSection'));

  const systemFields: { value: unknown; key: string; param: string }[] = [
    { value: sys.uptime, key: 'systemUptime', param: 'uptime' },
    { value: sys.memoryPercent, key: 'systemMemory', param: 'percent' },
    { value: sys.diskPercent, key: 'systemDisk', param: 'percent' },
    { value: sys.datastorePercent, key: 'systemDatastore', param: 'percent' },
  ];

  for (const field of systemFields) {
    if (field.value) {
      outputService.info(t(`commands.machine.health.${field.key}`, { [field.param]: field.value }));
    }
  }
}

function displayContainersSection(cont: MachineHealthResult['details']['containers']): void {
  if (cont.total === 0) return;

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

function displayServicesSection(svc: MachineHealthResult['details']['services']): void {
  if (svc.total === 0) return;

  outputService.info(t('commands.machine.health.servicesSection'));
  outputService.info(
    t('commands.machine.health.servicesSummary', {
      active: svc.active,
      total: svc.total,
      failed: svc.failed,
    })
  );
}

function displayStorageSection(stor: MachineHealthResult['details']['storage']): void {
  if (stor.smartHealthy === 0 && stor.smartFailing === 0) return;

  outputService.info(t('commands.machine.health.storageSection'));
  outputService.info(
    t('commands.machine.health.storageSmart', {
      healthy: stor.smartHealthy,
      failing: stor.smartFailing,
    })
  );
  if (stor.maxTemperature !== null) {
    outputService.info(t('commands.machine.health.storageTemp', { temp: stor.maxTemperature }));
  }
}

function displayRepositoriesSection(
  repositoryStats: MachineHealthResult['details']['repositories']
): void {
  if (repositoryStats.total === 0) return;

  outputService.info(t('commands.machine.health.repositoriesSection'));
  outputService.info(
    t('commands.machine.health.repositoriesSummary', {
      mounted: repositoryStats.mounted,
      total: repositoryStats.total,
      docker: repositoryStats.dockerRunning,
    })
  );
}

function displayIssuesSection(issues: string[]): void {
  if (issues.length === 0) return;

  outputService.info(t('commands.machine.health.issuesSection'));
  for (const issue of issues) {
    outputService.warn(`  - ${issue}`);
  }
}

function displayHealthReport(health: MachineHealthResult, name: string): void {
  outputService.info(t('commands.machine.health.header', { name }));
  displayStatusByExitCode(health.exitCode);
  displaySystemSection(health.details.system);
  displayContainersSection(health.details.containers);
  displayServicesSection(health.details.services);
  displayStorageSection(health.details.storage);
  displayRepositoriesSection(health.details.repositories);
  displayIssuesSection(health.issues);
  outputService.info(t('commands.machine.health.exitCode', { code: health.exitCode }));
}

export function registerHealthCommand(machine: Command, program: Command): void {
  machine
    .command('health <name>')
    .description(t('commands.machine.health.description'))
    .option('-t, --team <name>', t('options.team'))
    .action(async (name: string, options: { team?: string }) => {
      try {
        const provider = await getStateProvider();
        if (provider.mode === 'cloud') {
          await authService.requireAuth();
        }
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const machine = await withSpinner(
          t('commands.machine.health.fetching'),
          () =>
            provider.machines.getWithVaultStatus({
              teamName: opts.team as string,
              machineName: name,
            }),
          t('commands.machine.health.fetched')
        );

        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const format = program.opts().output as OutputFormat;
        const health = getMachineHealth(machine);

        if (format === 'json') {
          outputService.print(health, format);
        } else {
          displayHealthReport(health, name);
        }

        if (health.exitCode !== 0) {
          process.exitCode = health.exitCode;
        }
      } catch (error) {
        handleError(error);
      }
    });
}
