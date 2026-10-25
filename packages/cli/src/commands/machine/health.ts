import {
  getMachineHealth,
  type MachineHealthResult,
  parseListResult,
} from '@rediacc/shared/services/machine';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import type { StaleBackupRepo } from '../../services/backup/backup-schedule-coverage.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import type { RenetProcess } from '../../services/renet/renet-daemons.js';
import { getStateProvider } from '../../services/state.js';
import type { OutputFormat } from '../../types/index.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import { fetchStaleBackups, fetchStaleBinaries } from './status.js';

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

function displayLicensesSection(lic: MachineHealthResult['details']['licenses']): void {
  if (lic.total === 0) return;

  outputService.info(t('commands.machine.health.licensesSection'));
  outputService.info(
    t('commands.machine.health.licensesSummary', {
      valid: lic.valid,
      total: lic.total,
      expired: lic.expired,
      mismatch: lic.machineMismatch,
      missing: lic.missing,
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
  displayLicensesSection(health.details.licenses);
  displayIssuesSection(health.issues);
  outputService.info(t('commands.machine.health.exitCode', { code: health.exitCode }));
}

/** What the CLI adds to the vault-status health verdict: stale binaries (C4) and stale backups (G7). */
export interface HealthStaleness {
  staleBinary: RenetProcess[] | null;
  staleBackups: StaleBackupRepo[];
}

/**
 * Fold the staleness findings into a health result. Either kind is a warning (exit code at least 1):
 * a daemon on a deleted binary runs code the machine no longer has, and a repo two schedule intervals
 * behind is a backup that silently stopped.
 */
export function applyStaleness(
  health: MachineHealthResult,
  extra: HealthStaleness
): MachineHealthResult {
  const issues = [...health.issues];
  let exitCode = health.exitCode;
  const binaries = extra.staleBinary ?? [];
  if (binaries.length > 0) {
    issues.push(
      `${binaries.length} renet process(es) run a replaced binary: ${binaries.map((p) => `${p.unit} (pid ${p.pid})`).join(', ')}`
    );
    exitCode = Math.max(exitCode, 1);
  }
  if (extra.staleBackups.length > 0) {
    issues.push(
      `${extra.staleBackups.length} repository(ies) last backed up more than twice their schedule interval ago`
    );
    exitCode = Math.max(exitCode, 1);
  }
  // Raised from 0 only by these checks, so the shared verdict's message moves with it.
  const message = exitCode === health.exitCode ? health.message : 'System has warnings';
  return { ...health, issues, exitCode, healthy: exitCode === 0, message };
}

export function registerHealthCommand(machine: Command, program: Command): void {
  machine
    .command('health')
    .description(t('commands.machine.health.description'))
    .argument('<name>', t('options.name'))
    .option('-t, --team <name>', t('options.team'))
    .action(async (name: string, options: { team?: string }) => {
      try {
        const provider = getStateProvider();
        const opts = await configService.applyDefaults(options);

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
        const listResult = parseListResult(machine.vaultStatus);
        const [staleBinary, staleBackups] = await Promise.all([
          fetchStaleBinaries(name),
          listResult ? fetchStaleBackups(name, listResult) : Promise.resolve([]),
        ]);
        const health = applyStaleness(getMachineHealth(machine), { staleBinary, staleBackups });

        if (format === 'json') {
          outputService.print(
            { ...health, stale_binary: staleBinary, backup_staleness: staleBackups },
            format
          );
        } else {
          displayHealthReport(health, name);
        }

        if (health.exitCode !== 0) {
          setExitCode(health.exitCode);
        }
      } catch (error) {
        handleError(error);
      }
    });
}
